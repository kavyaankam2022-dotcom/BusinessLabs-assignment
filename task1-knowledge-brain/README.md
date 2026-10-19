# Task 1 — Knowledge Brain

This task implements the shared product knowledge layer for the AI Tech Consultant system.

## Purpose

- crawl product documentation and help pages
- parse text and image context from articles
- store searchable chunks with embeddings
- answer questions with grounded citations
- escalate when evidence is missing or insufficient

## Planned stack

- Python
- FastAPI or similar API layer
- BeautifulSoup / lxml for parsing
- vector database or PostgreSQL with pgvector
- embedding model configured through environment variables
- optional multimodal analysis for screenshot extraction

## API contract and independent test

See [API.md](API.md) for request and response field meanings, authentication, timeouts, error format, and curl examples. FastAPI also serves interactive OpenAPI documentation at `/docs`.

Run API tests independently of external services with:

```bash
python -m pytest task1-knowledge-brain/tests -q
```

## Priority order

1. sitemap inspection and resumable crawl
2. parsing article sections and metadata
3. image association and screenshot descriptions
4. chunking and retrieval indexing
5. RAG answer generation
6. API contract and escalation flow
7. scheduled refresh and deletion tracking

## Escalation and daily refresh

Unanswered questions become persisted expert tasks and pending evaluation cases. Expert-reviewed answers default to customer-specific, require the matching `customer_id` for retrieval, and may expire. Only an expert's explicit `general` applicability approval makes an answer globally searchable. Revisions retain older versions for audit while only the latest approved version stays active.

The FastAPI service schedules a daily sitemap check at 02:15 UTC. Configure the time with `KB_DAILY_INGESTION_HOUR_UTC` and `KB_DAILY_INGESTION_MINUTE_UTC`. Ingestion status includes recent reports and page-level failures. See [API.md](API.md) for escalation, evaluation-case, expert-version, and status endpoints.
