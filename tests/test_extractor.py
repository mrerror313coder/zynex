from extractor import extract_fields, find_deadline


def test_deadline_parsing():
    text = "Please apply by May 15, 2026. Late submissions will not be accepted."
    iso, phrase = find_deadline(text)
    assert iso == "2026-05-15"
    assert "May 15, 2026" in phrase


def test_multiple_deadlines_pick_earliest():
    text = "Deadline: 2026-06-01. Early applications close on 2026-05-10."
    iso, phrase = find_deadline(text)
    assert iso == "2026-05-10"
    assert "2026-05-10" in phrase


def test_extract_eligibility_and_documents():
    text = "Eligibility: BS/MS students with CGPA 3.7+. Submit CV, transcript, and portfolio."
    extracted = extract_fields(text)
    assert extracted["required_documents"] == ["cv", "transcript", "portfolio"]
    assert any("3.7" in item for item in extracted["eligibility"])
    assert any("bs" in item.lower() or "ms" in item.lower() for item in extracted["eligibility"])
