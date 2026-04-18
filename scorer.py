import re
from datetime import date, datetime
from typing import Dict, Optional


def days_until(deadline_iso: Optional[str]):
    if not deadline_iso:
        return None
    deadline = datetime.fromisoformat(deadline_iso)
    return (deadline.date() - date.today()).days


def _extract_required_cgpa(opportunity: Dict) -> Optional[float]:
    for item in opportunity.get("eligibility", []):
        if "cgpa" in item.lower() or "gpa" in item.lower():
            match = re.search(r"([0-4]\.?\d{0,2})", item)
            if match:
                return float(match.group(1))
    return None


def compute_score(opportunity: Dict, profile: Dict) -> Dict:
    fit = 0.0

    profile_degree = (profile.get("degree") or "").lower()
    profile_skills = {skill.lower() for skill in profile.get("skills", [])}
    preferred_types = {item.lower() for item in profile.get("preferred_types", [])}

    eligibility_text = " ".join(opportunity.get("eligibility", [])).lower()
    if profile_degree and profile_degree in eligibility_text:
        fit += 30
    elif profile_degree and any(token in eligibility_text for token in profile_degree.split()):
        fit += 15

    cgpa_req = _extract_required_cgpa(opportunity)
    if cgpa_req:
        try:
            student_cgpa = float(profile.get("cgpa", 0))
            fit += min(30, (student_cgpa / cgpa_req) * 30)
        except (TypeError, ValueError):
            pass

    required_skills = set()
    for token in re.findall(r"\b[a-zA-Z][a-zA-Z0-9_\-+]{1,}\b", eligibility_text):
        if token in profile_skills:
            required_skills.add(token)
    if required_skills:
        fit += min(30, (len(required_skills) / max(1, len(required_skills))) * 30)

    opportunity_type = (opportunity.get("opportunity_type") or "").lower()
    if opportunity_type in preferred_types:
        fit += 10

    fit = min(100, fit)

    days = days_until(opportunity.get("deadline"))
    if days is None:
        urgency = 20
    elif days <= 7:
        urgency = 100
    elif days <= 21:
        urgency = 70
    elif days <= 60:
        urgency = 40
    else:
        urgency = 10

    document_count = len(opportunity.get("required_documents", []))
    if document_count <= 1:
        effort = 100
    elif document_count == 2:
        effort = 80
    elif document_count == 3:
        effort = 60
    else:
        effort = 30

    impact = 0
    if opportunity.get("compensation"):
        impact += 60
    if opportunity_type in {"fellowship", "scholarship"}:
        impact += 40
    if opportunity_type == "internship" and "ai" in eligibility_text:
        impact += 15
    impact = min(100, impact)

    final = 0.4 * fit + 0.3 * urgency + 0.15 * effort + 0.15 * impact
    return {
        "final_score": round(final, 1),
        "breakdown": {
            "fit": round(fit, 1),
            "urgency": urgency,
            "effort": effort,
            "impact": impact,
        },
        "days_until_deadline": days,
    }


def generate_checklist(opportunity: Dict, score_obj: Dict, profile: Dict) -> Dict:
    final_score = score_obj.get("final_score", 0)
    if final_score >= 75:
        priority = "High"
    elif final_score >= 50:
        priority = "Medium"
    else:
        priority = "Low"

    days = score_obj.get("days_until_deadline")
    if days is None:
        deadline_line = "No deadline found"
    else:
        deadline_line = f"{opportunity.get('deadline')} ({days} days left)"

    documents = opportunity.get("required_documents") or []
    apply_target = None
    if opportunity.get("links"):
        apply_target = opportunity["links"][0]
    elif opportunity.get("contacts"):
        apply_target = f"email {opportunity['contacts'][0]}"
    else:
        apply_target = "check the original email"

    next_steps = [
        "Update CV using profile details",
        f"Draft a tailored motivation note for {opportunity.get('opportunity_type')}",
        f"Submit via {apply_target}",
    ]

    return {
        "priority": priority,
        "deadline_line": deadline_line,
        "why": opportunity.get("evidence", ""),
        "required_documents": documents,
        "next_steps": next_steps,
        "contact": opportunity.get("contacts", []),
        "apply_link": opportunity.get("links", []),
        "prefill_hints": {
            "name": profile.get("name"),
            "degree": profile.get("degree"),
            "skills": profile.get("skills", []),
        },
    }
