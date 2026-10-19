import asyncio
from dataclasses import replace

from fastapi.testclient import TestClient

from app import main


class StubStore:
    def __init__(self, evidence=None):
        self.evidence = evidence or []
        self.is_initialized = False
        self.escalations = []

    def initialize(self):
        self.is_initialized = True

    def search(self, question, embedder, top_k, customer_id=None):
        return self.evidence[:top_k]

    def create_escalation(self, request):
        self.escalations.append(request)
        return f"expert-{len(self.escalations)}"

    def start_ingestion_run(self, trigger):
        return f"run-{trigger}"

    def finish_ingestion_run(self, run_id, status, report=None, error=None):
        self.ingestion_run = (run_id, status, report, error)


def make_evidence():
    return [{
        "document_id": "doc-1",
        "chunk_id": "chunk-1",
        "title": "Logo settings",
        "url": "https://support.brilliantdirectories.com/article/logo",
        "section": "Branding",
        "excerpt": "Open the branding settings to change the logo.",
        "relevance": 0.73,
        "images": [{"url": "https://support.brilliantdirectories.com/logo.png", "description": "Logo setting screenshot"}],
    }]


def client_for(monkeypatch, evidence=None, answer="The source-supported answer."):
    store = StubStore(evidence)
    monkeypatch.setattr(main, "store", store)
    monkeypatch.setattr(main, "embedder", object())
    monkeypatch.setattr(main, "generate_answer", lambda question, sources: answer)
    monkeypatch.delenv("KB_API_KEY", raising=False)
    return TestClient(main.app), store


def test_query_returns_documented_grounded_response(monkeypatch):
    client, _ = client_for(monkeypatch, make_evidence())

    response = client.post("/query", json={"question": "How do I change the site logo?"})

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "answered"
    assert body["needs_human"] is False
    assert body["sources"][0]["url"].endswith("/article/logo")
    assert body["sources"][0]["relevance"] == 0.73
    assert body["image_references"][0]["url"].endswith("/logo.png")
    assert body["escalation_id"] is None
    assert "confidence" not in body
    assert response.headers["X-Request-ID"]


def test_missing_evidence_creates_expert_task(monkeypatch):
    client, store = client_for(monkeypatch)

    response = client.post("/query", json={"question": "Is there a built-in payroll feature?"})

    body = response.json()
    assert response.status_code == 200
    assert body["status"] == "insufficient_evidence"
    assert body["needs_human"] is True
    assert body["escalation_id"] == "expert-1"
    assert store.escalations[0].question == "Is there a built-in payroll feature?"


def test_answer_generation_failure_escalates_with_evidence(monkeypatch):
    client, store = client_for(monkeypatch, make_evidence(), answer=None)

    response = client.post("/query", json={"question": "How do I change the site logo?"})

    body = response.json()
    assert body["status"] == "needs_human"
    assert body["needs_human"] is True
    assert body["escalation_id"] == "expert-1"
    assert store.escalations[0].evidence[0]["chunk_id"] == "chunk-1"


def test_query_validation_returns_stable_error(monkeypatch):
    client, _ = client_for(monkeypatch)

    response = client.post("/query", json={"question": "  ", "top_k": 20})

    body = response.json()
    assert response.status_code == 422
    assert body["code"] == "validation_error"
    assert body["request_id"] == response.headers["X-Request-ID"]
    assert {item["field"] for item in body["errors"]} == {"question", "top_k"}


def test_configured_api_key_protects_query_but_not_health(monkeypatch):
    client, _ = client_for(monkeypatch, make_evidence())
    monkeypatch.setenv("KB_API_KEY", "test-secret")

    assert client.get("/health").status_code == 200
    denied = client.post("/query", json={"question": "How do I change the site logo?"})
    allowed = client.post(
        "/query",
        json={"question": "How do I change the site logo?"},
        headers={"X-API-Key": "test-secret"},
    )

    assert denied.status_code == 401
    assert denied.json()["code"] == "http_error"
    assert allowed.status_code == 200


def test_ingestion_timeout_returns_gateway_timeout(monkeypatch):
    client, _ = client_for(monkeypatch)
    monkeypatch.setattr(main, "settings", replace(main.settings, ingestion_job_timeout_seconds=0.001))

    async def slow_ingestion(**kwargs):
        await asyncio.sleep(0.05)

    monkeypatch.setattr(main, "run_ingestion", slow_ingestion)
    response = client.post("/ingestion/run", json={"max_pages": 1})

    assert response.status_code == 504
    assert response.json()["code"] == "http_error"
    assert response.json()["request_id"] == response.headers["X-Request-ID"]


def test_openapi_documents_query_contract(monkeypatch):
    client, _ = client_for(monkeypatch)

    schema = client.get("/openapi.json").json()

    query_schema = schema["components"]["schemas"]["QueryResponse"]["properties"]
    assert "escalation_id" in query_schema
    assert "confidence" not in query_schema
    assert schema["paths"]["/query"]["post"]["summary"]