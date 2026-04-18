import json
from pathlib import Path
from typing import List, Optional

from fastapi import FastAPI
from pydantic import BaseModel, Field

from classifier import is_opportunity
from extractor import extract_fields
from scorer import compute_score, generate_checklist

BASE_DIR = Path(__file__).resolve().parent
DEMO_EMAILS_PATH = BASE_DIR / "demo_emails.json"
PROFILE_PATH = BASE_DIR / "student_profile.json"

app = FastAPI(title="ZYNEX", version="1.0.0")


class AnalyzeRequest(BaseModel):
    emails: List[str] = Field(default_factory=list)
    profile: dict = Field(default_factory=dict)


class EmailResult(BaseModel):
    index: int
    is_opportunity: bool
    evidence_line: str
    extracted: dict
    score: Optional[dict] = None
    checklist: Optional[dict] = None


def load_json(path: Path):
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def run_pipeline(emails: List[str], profile: dict):
    results = []
    for index, email_text in enumerate(emails):
        classification, evidence_line = is_opportunity(email_text)
        extracted = extract_fields(email_text)
        score_obj = compute_score(extracted, profile) if classification else None
        checklist = generate_checklist(extracted, score_obj, profile) if score_obj else None

        results.append(
            {
                "index": index,
                "is_opportunity": classification,
                "evidence_line": evidence_line,
                "extracted": extracted,
                "score": score_obj,
                "checklist": checklist,
            }
        )

    ranked = [item for item in results if item["is_opportunity"]]
    ranked.sort(key=lambda item: item["score"]["final_score"] if item["score"] else 0, reverse=True)
    return ranked, [item for item in results if not item["is_opportunity"]]


@app.get("/")
def root():
    return {"message": "ZYNEX is running. Use /demo or POST /analyze."}


@app.get("/demo")
def demo():
    emails = load_json(DEMO_EMAILS_PATH)
    profile = load_json(PROFILE_PATH)
    ranked, filtered = run_pipeline(emails, profile)
    return {"profile": profile, "ranked": ranked, "filtered_out": filtered}


@app.post("/analyze")
def analyze(request: AnalyzeRequest):
    ranked, filtered = run_pipeline(request.emails, request.profile)
    return {"profile": request.profile, "ranked": ranked, "filtered_out": filtered}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("app:app", host="127.0.0.1", port=8000, reload=True)
