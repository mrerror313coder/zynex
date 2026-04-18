import json
import os
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, Optional, Tuple

import streamlit as st

AUDIT_DIR = Path(__file__).resolve().parent / "llm_audit"


def llm_is_active() -> Tuple[bool, str]:
    provider = (os.getenv("LLM_PROVIDER") or "").strip().lower()

    if provider == "gemini":
        key = os.getenv("GEMINI_API_KEY")
        model = os.getenv("GEMINI_MODEL") or "gemini-1.5-flash"
        return bool(key), f"gemini:{model}"

    if provider == "groq":
        key = os.getenv("GROQ_API_KEY")
        model = os.getenv("GROQ_MODEL") or "llama-3.1-8b-instant"
        return bool(key), f"groq:{model}"

    # OpenAI remains default provider when not specified.
    key = os.getenv("OPENAI_API_KEY") or os.getenv("LLM_API_KEY")
    model = os.getenv("OPENAI_MODEL") or os.getenv("LLM_MODEL") or "gpt-4o-mini"
    return bool(key), f"openai:{model}"


def latest_audit_file(audit_dir: Path = AUDIT_DIR) -> Optional[Path]:
    if not audit_dir.exists():
        return None
    files = sorted(audit_dir.glob("audit_*.json"), key=lambda path: path.stat().st_mtime, reverse=True)
    return files[0] if files else None


def read_audit_preview(path: Path, max_chars: int = 4000):
    try:
        with path.open("r", encoding="utf-8") as handle:
            data = json.load(handle)
        preview = {
            "timestamp": data.get("timestamp"),
            "email_id": data.get("email_id"),
            "model": data.get("model"),
            "status": data.get("status"),
            "prompt_snippet": (data.get("prompt_snippet") or "")[:500],
            "raw_output_snippet": (data.get("raw_output_snippet") or "")[:1000],
        }
        return preview, data
    except Exception as exc:
        return {"error": str(exc)}, None


def clear_old_audits(days: int = 30, audit_dir: Path = AUDIT_DIR):
    cutoff = datetime.now(UTC) - timedelta(days=days)
    removed = []
    if not audit_dir.exists():
        return removed

    for path in audit_dir.glob("audit_*.json"):
        modified = datetime.fromtimestamp(path.stat().st_mtime, UTC)
        if modified < cutoff:
            path.unlink()
            removed.append(str(path))
    return removed


def render_status_panel(sidebar=st.sidebar):
    sidebar.markdown("### System status")
    active, model = llm_is_active()
    sidebar.write("**LLM Mode**: " + ("**Active**" if active else "**Disabled**"))
    sidebar.write("**Model**: " + str(model))

    latest = latest_audit_file()
    if latest:
        sidebar.write("**Latest audit**: " + latest.name)

        preview_key = "preview_latest_audit"
        if sidebar.button("Preview latest audit", key=preview_key):
            preview, full = read_audit_preview(latest)
            sidebar.json(preview)
            if full is not None:
                sidebar.download_button(
                    "Download latest audit",
                    data=json.dumps(full, ensure_ascii=False, indent=2),
                    file_name=latest.name,
                    mime="application/json",
                )
                sidebar.json(full)
    else:
        sidebar.write("No audit records found")

    clear_key = "clear_old_audits"
    if sidebar.button("Clear audits older than 90 days", key=clear_key):
        removed = clear_old_audits(days=90)
        sidebar.write(f"Removed {len(removed)} files")