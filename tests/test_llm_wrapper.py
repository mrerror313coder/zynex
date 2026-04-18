import llm_wrapper


def test_parse_json_from_model_handles_json_block():
    payload = llm_wrapper.parse_json_from_model('noise {"opportunity_type": "internship", "deadline_iso": null, "eligibility_list": [], "required_documents": [], "contacts": [], "links": [], "evidence": "ok"} trailing')
    assert payload is not None
    assert payload["opportunity_type"] == "internship"


def test_llm_extract_uses_valid_payload(monkeypatch):
    monkeypatch.setattr(
        llm_wrapper,
        "call_llm_api",
        lambda prompt_text: '{"opportunity_type":"internship","deadline_iso":"2026-05-15","deadline_phrase":"Apply by May 15, 2026","eligibility_list":["CGPA >= 3.5"],"required_documents":["CV"],"contacts":["hr@example.com"],"links":["https://example.com"],"location":"Lahore","compensation":"Paid internship","evidence":"Apply by May 15, 2026"}',
    )

    payload, status = llm_wrapper.llm_extract("Sample email text")
    assert status == "ok"
    assert payload["deadline_iso"] == "2026-05-15"


def test_llm_extract_reports_unavailable(monkeypatch):
    def raise_error(prompt_text):
        raise RuntimeError("no api key")

    monkeypatch.setattr(llm_wrapper, "call_llm_api", raise_error)
    payload, status = llm_wrapper.llm_extract("Sample email text")
    assert payload is None
    assert status == "llm_unavailable"