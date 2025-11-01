from backend.services.llm import StubLLMClient


def test_stub_llm_extract_job_json_basic():
    text = """Title: Senior Support Engineer\nCompany: Acme Corp\nLocation: Remote\nMust have: Python\nMust have: FastAPI\nNice to have: Playwright\nDo you automate workflows?"""
    client = StubLLMClient()
    extraction = client.extract_job_json(text)
    payload = extraction.to_json()

    assert "Senior Support Engineer" in payload
    assert "Acme Corp" in payload
    assert "Python" in payload
    assert "Playwright" in payload
