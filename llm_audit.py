import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

AUDIT_DIR = Path(__file__).resolve().parent / "llm_audit"


def audit_record(email_id: str, prompt: str, model_name: str, raw_output: str, parsed_json: Any, status: str) -> str:
    AUDIT_DIR.mkdir(exist_ok=True)
    now = datetime.now(UTC)
    record = {
        "timestamp": now.isoformat(),
        "email_id": email_id,
        "model": model_name,
        "status": status,
        "prompt_snippet": prompt[:1000],
        "raw_output_snippet": raw_output[:2000],
        "parsed_json": parsed_json,
    }
    file_name = AUDIT_DIR / f"audit_{email_id}_{int(now.timestamp())}.json"
    with file_name.open("w", encoding="utf-8") as handle:
        json.dump(record, handle, ensure_ascii=False, indent=2)
    return str(file_name)