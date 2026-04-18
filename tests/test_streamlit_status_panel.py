import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import streamlit_status_panel as status_panel


def test_read_audit_preview_returns_summary(tmp_path):
    audit_path = tmp_path / "audit_sample.json"
    payload = {
        "timestamp": "2026-04-18T00:00:00Z",
        "email_id": "sample-1",
        "model": "gpt-test",
        "status": "ok",
        "prompt_snippet": "prompt text",
        "raw_output_snippet": "raw text",
        "parsed_json": {"ok": True},
    }
    audit_path.write_text(json.dumps(payload), encoding="utf-8")

    preview, full = status_panel.read_audit_preview(audit_path)

    assert preview["email_id"] == "sample-1"
    assert preview["status"] == "ok"
    assert full["parsed_json"] == {"ok": True}


def test_clear_old_audits_removes_only_stale_files(tmp_path):
    old_file = tmp_path / "audit_old.json"
    new_file = tmp_path / "audit_new.json"
    old_file.write_text("{}", encoding="utf-8")
    new_file.write_text("{}", encoding="utf-8")

    old_timestamp = datetime.now(UTC) - timedelta(days=100)
    new_timestamp = datetime.now(UTC) - timedelta(days=1)
    old_epoch = old_timestamp.timestamp()
    new_epoch = new_timestamp.timestamp()

    Path(old_file).touch()
    Path(new_file).touch()
    import os

    os.utime(old_file, (old_epoch, old_epoch))
    os.utime(new_file, (new_epoch, new_epoch))

    removed = status_panel.clear_old_audits(days=90, audit_dir=tmp_path)

    assert str(old_file) in removed
    assert new_file.exists()
    assert not old_file.exists()


def test_latest_audit_file_picks_newest(tmp_path):
    first = tmp_path / "audit_a.json"
    second = tmp_path / "audit_b.json"
    first.write_text("{}", encoding="utf-8")
    second.write_text("{}", encoding="utf-8")

    os = __import__("os")
    first_time = (datetime.now(UTC) - timedelta(days=2)).timestamp()
    second_time = datetime.now(UTC).timestamp()
    os.utime(first, (first_time, first_time))
    os.utime(second, (second_time, second_time))

    latest = status_panel.latest_audit_file(tmp_path)

    assert latest == second