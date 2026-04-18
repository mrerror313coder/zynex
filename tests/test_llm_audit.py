from pathlib import Path

import llm_audit


def test_audit_record_writes_file(tmp_path, monkeypatch):
    monkeypatch.setattr(llm_audit, "AUDIT_DIR", tmp_path)

    file_path = llm_audit.audit_record(
        email_id="email-1",
        prompt="prompt text",
        model_name="gpt-4o-mini",
        raw_output='{"ok": true}',
        parsed_json={"ok": True},
        status="ok",
    )

    written = Path(file_path)
    assert written.exists()
    content = written.read_text(encoding="utf-8")
    assert '"status": "ok"' in content
    assert '"email_id": "email-1"' in content