import json
import os
import re
import threading
import time
from hashlib import sha256
from typing import Any, Dict, Optional, Tuple

from jsonschema import ValidationError, validate
from dotenv import load_dotenv

from llm_audit import audit_record

load_dotenv()

SCHEMA = {
    "type": "object",
    "properties": {
        "opportunity_type": {
            "type": "string",
            "enum": ["internship", "scholarship", "competition", "fellowship", "job", "unknown"],
        },
        "deadline_iso": {"anyOf": [{"type": "string"}, {"type": "null"}]},
        "deadline_phrase": {"anyOf": [{"type": "string"}, {"type": "null"}]},
        "eligibility_list": {"type": "array", "items": {"type": "string"}},
        "required_documents": {"type": "array", "items": {"type": "string"}},
        "contacts": {"type": "array", "items": {"type": "string"}},
        "links": {"type": "array", "items": {"type": "string"}},
        "location": {"anyOf": [{"type": "string"}, {"type": "null"}]},
        "compensation": {"anyOf": [{"type": "string"}, {"type": "null"}]},
        "evidence": {"type": "string"},
    },
    "required": ["opportunity_type", "deadline_iso", "eligibility_list", "required_documents", "contacts", "links", "evidence"],
    "additionalProperties": True,
}

PROMPT_TEMPLATE = """You are an information extraction assistant. Extract the following fields from the email text and return valid JSON only, with these keys:
opportunity_type, deadline_iso, deadline_phrase, eligibility_list, required_documents, contacts, links, location, compensation, evidence

- opportunity_type: one of ["internship","scholarship","competition","fellowship","job","unknown"]
- deadline_iso: ISO date string YYYY-MM-DD or null
- deadline_phrase: the exact phrase from the email that indicates the deadline or null
- eligibility_list: array of short strings (e.g., "CGPA >= 3.5", "final-year CS")
- required_documents: array of short strings (e.g., "CV", "transcript")
- contacts: array of emails or phone numbers
- links: array of URLs
- location: short string or null
- compensation: short string or null
- evidence: for each non-null field include the exact sentence or clause from the email that supports it; put these evidence snippets in a single string separated by " || " if multiple.

Return only JSON. Do not add commentary."""

_LLM_CALL_LOCK = threading.Lock()
_LAST_LLM_CALL_AT = 0.0


def _get_llm_provider() -> str:
    provider = (os.getenv("LLM_PROVIDER") or "").strip().lower()
    if provider in {"openai", "gemini", "groq"}:
        return provider
    if os.getenv("GEMINI_API_KEY"):
        return "gemini"
    if os.getenv("GROQ_API_KEY"):
        return "groq"
    return "openai"


def _get_active_model_name(provider: str) -> str:
    if provider == "gemini":
        return os.getenv("GEMINI_MODEL", "gemini-1.5-flash")
    if provider == "groq":
        return os.getenv("GROQ_MODEL", "llama-3.1-8b-instant")
    return os.getenv("OPENAI_MODEL", "gpt-4o-mini")


def _call_openai(prompt_text: str, model: str, timeout_seconds: float) -> str:
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY is not set")

    try:
        from openai import OpenAI
    except ImportError as exc:
        raise RuntimeError("openai package is not installed") from exc

    client = OpenAI(api_key=api_key)
    response = client.chat.completions.create(
        model=model,
        temperature=0,
        timeout=timeout_seconds,
        messages=[
            {"role": "system", "content": "You extract structured fields from opportunity emails."},
            {"role": "user", "content": prompt_text},
        ],
    )
    return response.choices[0].message.content or ""


def _call_gemini(prompt_text: str, model: str) -> str:
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        raise RuntimeError("GEMINI_API_KEY is not set")

    try:
        import google.generativeai as genai
    except ImportError as exc:
        raise RuntimeError("google-generativeai package is not installed") from exc

    genai.configure(api_key=api_key)
    gemini_model = genai.GenerativeModel(model_name=model)
    response = gemini_model.generate_content(prompt_text, generation_config={"temperature": 0})
    text = getattr(response, "text", None)
    if text:
        return text

    # Fallback for SDK responses that expose parts rather than text.
    candidates = getattr(response, "candidates", []) or []
    parts = []
    for candidate in candidates:
        content = getattr(candidate, "content", None)
        if not content:
            continue
        for part in getattr(content, "parts", []) or []:
            part_text = getattr(part, "text", None)
            if part_text:
                parts.append(part_text)
    return "\n".join(parts)


def _call_groq(prompt_text: str, model: str, timeout_seconds: float) -> str:
    api_key = os.getenv("GROQ_API_KEY")
    if not api_key:
        raise RuntimeError("GROQ_API_KEY is not set")

    try:
        from groq import Groq
    except ImportError as exc:
        raise RuntimeError("groq package is not installed") from exc

    client = Groq(api_key=api_key)
    response = client.chat.completions.create(
        model=model,
        temperature=0,
        timeout=timeout_seconds,
        messages=[
            {"role": "system", "content": "You extract structured fields from opportunity emails."},
            {"role": "user", "content": prompt_text},
        ],
    )
    return response.choices[0].message.content or ""


def call_llm_api(prompt_text: str) -> str:
    provider = _get_llm_provider()
    model = _get_active_model_name(provider)
    timeout_seconds = float(os.getenv("LLM_TIMEOUT_SECONDS", "10"))
    min_interval_seconds = float(os.getenv("LLM_MIN_INTERVAL_SECONDS", "0"))

    global _LAST_LLM_CALL_AT
    if min_interval_seconds > 0:
        with _LLM_CALL_LOCK:
            now = time.monotonic()
            wait_seconds = min_interval_seconds - (now - _LAST_LLM_CALL_AT)
            if wait_seconds > 0:
                time.sleep(wait_seconds)
            _LAST_LLM_CALL_AT = time.monotonic()

    if provider == "gemini":
        return _call_gemini(prompt_text, model)
    if provider == "groq":
        return _call_groq(prompt_text, model, timeout_seconds)
    return _call_openai(prompt_text, model, timeout_seconds)


def parse_json_from_model(text: str) -> Optional[Dict[str, Any]]:
    match = re.search(r"(\{[\s\S]*\})", text)
    if not match:
        return None
    try:
        parsed = json.loads(match.group(1))
    except json.JSONDecodeError:
        return None
    return parsed if isinstance(parsed, dict) else None


def _email_id_for_audit(email_text: str, email_id: Optional[str]) -> str:
    if email_id:
        return email_id
    return sha256(email_text.encode("utf-8")).hexdigest()[:12]


def _status_from_exception(exc: Exception) -> str:
    name = type(exc).__name__.lower()
    message = str(exc).lower()

    if "auth" in name or "invalid_api_key" in message or "incorrect api key" in message:
        return "llm_auth_failed"
    if "notfound" in name or "model" in message and "not found" in message:
        return "llm_model_not_found"
    if "resourceexhausted" in name or "quota" in message or "429" in message:
        return "llm_quota_exceeded"
    if "timeout" in name:
        return "llm_timeout"
    return "llm_unavailable"


def llm_extract(email_text: str, email_id: Optional[str] = None) -> Tuple[Optional[Dict[str, Any]], str]:
    audit_email_id = _email_id_for_audit(email_text, email_id)
    provider = _get_llm_provider()
    model_name = _get_active_model_name(provider)
    prompt = f"{PROMPT_TEMPLATE}\n\nEmail:\n\"\"\"\n{email_text}\n\"\"\"\n\nReturn JSON only."
    try:
        model_out = call_llm_api(prompt)
    except Exception as exc:
        status = _status_from_exception(exc)
        audit_record(audit_email_id, prompt, model_name, str(exc), None, status)
        return None, status

    parsed = parse_json_from_model(model_out)
    if not parsed:
        audit_record(audit_email_id, prompt, model_name, model_out, None, "llm_parse_failed")
        return None, "llm_parse_failed"

    try:
        validate(parsed, SCHEMA)
    except ValidationError:
        audit_record(audit_email_id, prompt, model_name, model_out, parsed, "llm_schema_failed")
        return None, "llm_schema_failed"

    audit_record(audit_email_id, prompt, model_name, model_out, parsed, "ok")
    return parsed, "ok"