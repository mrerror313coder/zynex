from scorer import compute_score, generate_checklist


def test_no_deadline_urgency_fallback():
    opportunity = {
        "opportunity_type": "internship",
        "deadline": None,
        "eligibility": ["CGPA 3.5"],
        "required_documents": ["cv"],
        "contacts": [],
        "links": [],
        "compensation": None,
        "evidence": "Example",
    }
    profile = {"degree": "BS Computer Science", "cgpa": 3.6, "preferred_types": ["internship"]}
    score = compute_score(opportunity, profile)
    assert score["breakdown"]["urgency"] == 20
    assert score["final_score"] > 0


def test_better_fit_scores_higher():
    profile = {
        "degree": "BS Computer Science",
        "cgpa": 3.6,
        "preferred_types": ["internship", "scholarship"],
    }
    strong = {
        "opportunity_type": "internship",
        "deadline": "2026-05-15",
        "eligibility": ["BS Computer Science", "CGPA 3.5"],
        "required_documents": ["cv", "transcript"],
        "contacts": [],
        "links": ["https://example.com"],
        "compensation": "Stipend/paid",
        "evidence": "Strong match",
    }
    weak = {
        "opportunity_type": "job",
        "deadline": "2026-07-01",
        "eligibility": ["MS Physics", "CGPA 3.9"],
        "required_documents": ["cv", "transcript", "portfolio", "references"],
        "contacts": [],
        "links": [],
        "compensation": None,
        "evidence": "Weak match",
    }
    assert compute_score(strong, profile)["final_score"] > compute_score(weak, profile)["final_score"]


def test_checklist_generation():
    opportunity = {
        "opportunity_type": "scholarship",
        "deadline": "2026-06-01",
        "eligibility": ["CGPA 3.7"],
        "required_documents": ["cv", "transcript"],
        "contacts": ["hr@example.com"],
        "links": ["https://example.com"],
        "compensation": "Stipend/paid",
        "evidence": "Scholarship email",
    }
    profile = {"name": "Muhammad", "degree": "BS Computer Science", "skills": ["python"], "cgpa": 3.6}
    score = compute_score(opportunity, profile)
    checklist = generate_checklist(opportunity, score, profile)
    assert checklist["priority"] in {"High", "Medium", "Low"}
    assert checklist["required_documents"] == ["cv", "transcript"]
    assert checklist["apply_link"] == ["https://example.com"]
