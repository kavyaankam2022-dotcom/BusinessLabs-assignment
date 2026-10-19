import os

import httpx

from .models import KnowledgeQueryResult


class KnowledgeBrainClient:
    def __init__(self, base_url: str | None = None, timeout_seconds: float = 20.0) -> None:
        self.base_url = (base_url or os.getenv("KB_API_URL", "http://127.0.0.1:8000")).rstrip("/")
        self.timeout_seconds = timeout_seconds

    async def query(self, question: str) -> KnowledgeQueryResult:
        headers = {"Content-Type": "application/json"}
        api_key = os.getenv("KB_API_KEY")
        if api_key:
            headers["X-API-Key"] = api_key
        try:
            async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
                response = await client.post(
                    f"{self.base_url}/query",
                    headers=headers,
                    json={"question": question[:4000], "customer_context": "Internal project feasibility review.", "top_k": 5},
                )
            if response.status_code >= 400:
                return KnowledgeQueryResult(status="unavailable", error=f"Knowledge Brain returned HTTP {response.status_code}.")
            return KnowledgeQueryResult.model_validate(response.json())
        except (httpx.TimeoutException, httpx.NetworkError):
            return KnowledgeQueryResult(status="unavailable", error="Knowledge Brain is unavailable or timed out.")
        except Exception:
            return KnowledgeQueryResult(status="unavailable", error="Knowledge Brain returned an invalid response.")
