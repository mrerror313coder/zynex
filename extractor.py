import re
from datetime import datetime
from typing import Dict, List, Optional, Tuple

import dateparser

from llm_wrapper import llm_extract

DOC_KEYWORDS = ["cv", "resume", "transcript", "sop", "statement of purpose", "portfolio", "references", "motivation letter"]
TYPE_MAP = {
    "internship": ["internship", "intern"],
    "scholarship": ["scholarship", "grant", "financial aid"],
    "competition": ["competition", "contest", "hackathon", "challenge"],
    "fellowship": ["fellowship"],
    "job": ["job", "position", "role", "opening"],
}

EMAIL_RE = re.compile(r"[\w\.-]+@[\w\.-]+\.\w+")
URL_RE = re.compile(r"https?://[^\s,;]+")
CGPA_RE = re.compile(r"(?:CGPA|GPA)\s*(?:>=|>|:|is)?\s*([0-4]\.?\d{0,2})\+?", re.I)
DEGREE_RE = re.compile(
    r"\b(bachelor|bachelors|master|masters|phd|bs|ms|bsc|msc|final year|final-year|senior|junior|first year|second year)\b",
    re.I,
)
DATE_PHRASE_RE = re.compile(
    r"(?:by|before|until|deadline[:\s]|apply by|applications close(?: on)?|register by)\s*([A-Za-z0-9,./\-\s]+)",
    re.I,
)
STANDALONE_DATE_RE = re.compile(
    r"\b(?:\d{1,2}[/-]\d{1,2}[/-]\d{2,4}|\d{4}-\d{2}-\d{2}|[A-Za-z]{3,9}\s+\d{1,2}(?:,\s*\d{4})?|\d{1,2}\s+[A-Za-z]{3,9}(?:\s+\d{4})?)\b"
)


def _parse_candidate(candidate: str) -> Optional[str]:
    parsed = dateparser.parse(candidate, settings={"PREFER_DATES_FROM": "future"})
    if not parsed:
        return None
    return parsed.date().isoformat()


def find_deadline(text: str) -> Tuple[Optional[str], Optional[str]]:
    candidates: List[str] = []

    for match in DATE_PHRASE_RE.finditer(text):
        phrase = match.group(1).strip(" .,:;\n\t")
        if phrase:
            candidates.append(phrase)

    for match in STANDALONE_DATE_RE.finditer(text):
        candidates.append(match.group(0).strip())

    parsed_candidates: List[Tuple[str, str]] = []
    for candidate in candidates:
        iso = _parse_candidate(candidate)
        if iso:
            parsed_candidates.append((iso, candidate))

    if not parsed_candidates:
        return None, None

    parsed_candidates.sort(key=lambda item: item[0])
    return parsed_candidates[0]


def _extract_type(text: str) -> str:
    lower = text.lower()
    for opportunity_type, keywords in TYPE_MAP.items():
        for keyword in keywords:
            if keyword in lower:
                return opportunity_type
    return "unknown"


def _extract_eligibility(text: str) -> List[str]:
    eligibility: List[str] = []
    cgpa_match = CGPA_RE.search(text)
    if cgpa_match:
        eligibility.append(f"CGPA {cgpa_match.group(1)}")

    degree_matches = DEGREE_RE.findall(text)
    seen = set()
    for match in degree_matches:
        normalized = match.strip()
        if normalized.lower() not in seen:
            eligibility.append(normalized)
            seen.add(normalized.lower())

    return eligibility


def _extract_documents(text: str) -> List[str]:
    lower = text.lower()
    documents: List[str] = []
    for keyword in DOC_KEYWORDS:
        if keyword in lower and keyword not in documents:
            documents.append(keyword)
    return documents


def _extract_raw_evidence_lines(text: str) -> List[str]:
    evidence_lines: List[str] = []
    for line in text.splitlines():
        line_lower = line.lower()
        if any(keyword in line_lower for keyword in ["apply", "deadline", "eligibility", "requirements", "stipend", "register", "scholarship", "internship", "hackathon", "competition"]):
            cleaned = line.strip()
            if cleaned:
                evidence_lines.append(cleaned)
    return evidence_lines or ([text.strip()] if text.strip() else [])


def _merge_list_values(*value_lists: List[str]) -> List[str]:
    merged: List[str] = []
    seen = set()
    for values in value_lists:
        for value in values:
            normalized = value.strip().lower()
            if normalized not in seen:
                merged.append(value)
                seen.add(normalized)
    return merged


def _merge_extractions(rule_data: Dict, llm_data: Optional[Dict]) -> Dict:
    if not llm_data:
        return rule_data

    merged = dict(rule_data)
    merged["opportunity_type"] = llm_data.get("opportunity_type") or rule_data.get("opportunity_type", "unknown")
    merged["deadline"] = llm_data.get("deadline_iso") or rule_data.get("deadline")
    merged["deadline_phrase"] = llm_data.get("deadline_phrase") or rule_data.get("deadline_phrase")
    merged["eligibility"] = _merge_list_values(rule_data.get("eligibility", []), llm_data.get("eligibility_list", []))
    merged["required_documents"] = _merge_list_values(rule_data.get("required_documents", []), llm_data.get("required_documents", []))
    merged["contacts"] = _merge_list_values(rule_data.get("contacts", []), llm_data.get("contacts", []))
    merged["links"] = _merge_list_values(rule_data.get("links", []), llm_data.get("links", []))
    merged["location"] = llm_data.get("location") or rule_data.get("location")
    merged["compensation"] = llm_data.get("compensation") or rule_data.get("compensation")
    evidence = llm_data.get("evidence") or ""
    if evidence:
        merged["evidence"] = f"{rule_data.get('evidence', '')}\nLLM: {evidence}".strip()
    merged["llm_status"] = "ok"
    return merged


def extract_fields(text: str) -> Dict:
    rule_deadline_iso, rule_deadline_phrase = find_deadline(text)
    opportunity_type = _extract_type(text)
    eligibility = _extract_eligibility(text)
    documents = _extract_documents(text)
    contacts = EMAIL_RE.findall(text)
    links = URL_RE.findall(text)
    lower = text.lower()

    compensation = None
    if any(keyword in lower for keyword in ["stipend", "paid", "salary", "compensation", "prize"]):
        compensation = "Stipend/paid"

    location = None
    location_match = re.search(r"\b(?:in|location|based in)\s+([A-Z][A-Za-z\s]+?)(?:[\.,;\n]|$)", text)
    if location_match:
        location = location_match.group(1).strip()

    rule_data = {
        "opportunity_type": opportunity_type,
        "deadline": rule_deadline_iso,
        "deadline_phrase": rule_deadline_phrase,
        "eligibility": eligibility,
        "required_documents": documents,
        "contacts": contacts,
        "links": links,
        "location": location,
        "compensation": compensation,
        "raw_evidence_lines": _extract_raw_evidence_lines(text),
        "evidence": text[:400],
        "llm_status": "fallback_only",
    }

    llm_data, status = llm_extract(text)
    if status == "ok":
        return _merge_extractions(rule_data, llm_data)

    rule_data["llm_status"] = status
    return rule_data
