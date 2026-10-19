# Knowledge Brain API

Base URL for local development: `http://127.0.0.1:8000`. Interactive OpenAPI documentation is available at `/docs`; the machine-readable schema is at `/openapi.json`.

Start the service from the repository root after installing Task 1 dependencies:

```powershell
py -m pip install -r task1-knowledge-brain/requirements.txt
py -m uvicorn app.main:app --app-dir task1-knowledge-brain --host 127.0.0.1 --port 8000
```

## Authentication and request IDs

Set `KB_API_KEY` in the service environment to require the `X-API-Key` header on every route except `GET /health`. If the variable is unset, authentication is disabled for local development. Configure it for shared or deployed environments, keep it out of source control, and use HTTPS in deployment.

Every response includes `X-Request-ID`. Clients may supply this header to correlate a request with server logs. Error responses also include the request ID in the JSON body.

## Query contract

`POST /query` accepts a product question and optional retrieval/context controls:

```json
{
  "question": "How do I change the site logo?",
  "top_k": 5,
  "customer_context": "The customer is editing their own site."
}
```

`question` must contain 3-4000 non-whitespace characters. `top_k` is optional and must be from 1 to 15. `customer_context` is optional and limited to 4000 characters.

Successful HTTP responses use this shape:

```json
{
  "answer": "The supported steps, based only on the cited material.",
  "status": "answered",
  "sources": [
    {
      "document_id": "stable-document-id",
      "chunk_id": "stable-chunk-id",
      "title": "Relevant article",
      "url": "https://support.brilliantdirectories.com/...",
      "section": "Settings",
      "excerpt": "Relevant source passage.",
      "relevance": 0.73,
      "images": []
    }
  ],
  "image_references": [],
  "needs_human": false,
  "escalation_reason": null,
  "escalation_id": null
}
```

Field meanings:

| Field | Meaning |
|---|---|
| `answer` | Grounded response text. It must not be treated as a product fact without its cited evidence. |
| `status` | `answered` means an answer was generated from retrieved evidence; `insufficient_evidence` means no relevant indexed evidence was found; `needs_human` means evidence was found but answer generation was unavailable or failed. |
| `sources` | Retrieved article or reviewed expert-answer chunks. IDs are stable within the source version; `url` identifies the source and `excerpt` is the supporting passage. |
| `sources[].relevance` | Hybrid retrieval ranking score from 0 to 1. It is not a probability that the answer is correct and must not be interpreted as calibrated confidence. |
| `image_references` | Image URLs and their associated descriptions from retrieved evidence. |
| `needs_human` | Whether a human should handle or approve this query. It is true for both non-answered statuses. |
| `escalation_reason` | Why the service could not safely return an answer; null when answered. |
| `escalation_id` | Persisted open expert task ID when `needs_human` is true; use it to resolve the task. |

There is deliberately no `confidence` field. The retrieval score is not calibrated answer confidence; a confidence value can be added only after a documented calibration and evaluation process.

Both non-answered statuses create an open escalation before the response is returned. The customer context and retrieved evidence, when present, are stored with the task. A service failure during retrieval or persistence returns an API error instead of a fabricated answer.

## Endpoints

| Method and path | Purpose |
|---|---|
| `GET /health` | Liveness check; does not require API key. |
| `POST /query` | Retrieve evidence, generate a grounded response, and persist an escalation if needed. |
| `POST /ingestion/run` | Start a sitemap crawl. Optional body: `{"max_pages": 20}` for a bounded test crawl. Full sitemap processing should omit `max_pages`. |
| `GET /ingestion/status` | Return page counts, active chunk count, and recent failures. |
| `POST /escalations` | Create an expert task manually. Required fields: `question`, `reason`; `evidence` and `customer_context` are optional. |
| `POST /escalations/{id}/resolve` | Record a reviewed answer. Requires `answer` and `reviewed_by`; optional `source_url` and `expires_at`. A successful resolution adds the reviewed answer to retrieval. |

## Errors and timeouts

All API errors use a stable envelope:

```json
{
  "code": "validation_error",
  "message": "Request validation failed.",
  "request_id": "correlation-id",
  "errors": [
    { "field": "top_k", "message": "Input should be less than or equal to 15", "type": "less_than_equal" }
  ]
}
```

`errors` is present for validation failures and may be omitted otherwise. The API returns `400` for an unsupported ingestion host, `401` for missing/invalid configured API key, `422` for invalid request data, `500` for an unexpected internal failure, `502` for an upstream sitemap/article fetch or parse failure, and `504` if the ingestion job exceeds its limit. Internal exception details are not returned to clients.

Claude requests have a default 20-second timeout, configurable with `KB_ANSWER_TIMEOUT_SECONDS`. A model timeout/failure becomes a persisted `needs_human` response when evidence was retrieved. Ingestion HTTP requests have a 30-second network timeout and retry temporary failures; the total ingestion API call is bounded by `KB_INGESTION_TIMEOUT_SECONDS` (default 300 seconds). A timed-out ingestion request can be retried; page-level checkpoints make the job resumable.

## Example calls

Query (add `-H "X-API-Key: $env:KB_API_KEY"` in PowerShell when authentication is configured):

```powershell
Invoke-RestMethod -Method Post -Uri http://127.0.0.1:8000/query `
  -ContentType "application/json" `
  -Body '{"question":"How do I change the site logo?","top_k":5}'
```

Start with a small crawl before the full sitemap:

```powershell
Invoke-RestMethod -Method Post -Uri http://127.0.0.1:8000/ingestion/run `
  -ContentType "application/json" `
  -Body '{"max_pages":20}'
```

The API can be tested independently of downstream tasks and external services:

```powershell
py -m pytest task1-knowledge-brain/tests -q
```

## Human escalation and reviewed knowledge

Unanswered questions are saved as open expert tasks with the original question, evidence, reason, optional customer context, and customer ID. They also create a pending evaluation case, available from `GET /evaluation/cases?status=pending`. The human queue is available from `GET /escalations?status=open`.

The `/escalations/{id}/resolve` request requires `answer`, `reviewed_by`, and an explicit applicability choice. Use `"applicability": "customer_specific"` with a `customer_id` unless an expert has confirmed that the answer is broadly applicable; only then use `"applicability": "general"`. Optional `supporting_evidence` and `source_url` are retained with the review. A timezone-aware future `expires_at` automatically removes an answer from retrieval when it expires.

Each approved answer is stored separately from crawled articles. The first approved record is version 1. `POST /expert-knowledge/{knowledge_id}/revise` creates a new version, preserves prior review history, and replaces the active retrieval record. `GET /expert-knowledge/{knowledge_id}/versions` lists retained versions.

## Scheduled ingestion

The service schedules a sitemap refresh daily at 02:15 UTC by default. Configure it with `KB_DAILY_INGESTION_HOUR_UTC` and `KB_DAILY_INGESTION_MINUTE_UTC`. Pages with unchanged sitemap `lastmod` are skipped; pages without it are checked by content hash. Failed pages are retried on later runs. Changed articles replace active chunks, and removed sitemap URLs are deactivated. Ingestion status includes recent reports with `added`, `updated`, `unchanged`, `removed`, and `failed` counts for both scheduled and manual runs.

Image URL, alt text, and nearby context contribute to the article content hash. Image bytes are not currently downloaded and checksummed, so a silent binary change at an unchanged image URL is not detected unless the page metadata changes.

Review an evaluation case with `POST /evaluation/cases/{escalation_id}/review` using `actual_result`, `passed`, and `reviewed_by`. The pending case retains the original question and expected behavior; the reviewed record adds the observed result, outcome, reviewer, and timestamp.