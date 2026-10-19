# Design Overview

## Business problem

The capstone is about three connected business workflows: answering product questions, reviewing customer emails, and converting meeting notes into a structured scope proposal. Each workflow depends on the same product truth: what the business supports today, what is missing, and what needs human review.

## Why the shared Knowledge Brain matters

Task 1 is the single source of truth for product knowledge. Task 2 and Task 3 are clients to that service rather than separate retrieval systems. This matters because the same answer should be available to support, sales, and delivery teams without each team building its own knowledge logic.

The result is: one retrieval layer, one citation system, one escalation path, and easier updates when product documentation changes.

## System architecture

```text
User / reviewer
       |
       v
+-------------------------------+
| Task 2: Inbox Agent           |
| - classify email              |
| - query shared knowledge      |
| - draft response              |
| - human review + approval     |
+---------------+---------------+
                |
                | HTTP / JSON
                v
+-------------------------------+
| Task 1: Knowledge Brain       |
| - ingest docs/sitemap         |
| - parse article content       |
| - retrieve evidence           |
| - answer with citations       |
| - escalate missing evidence   |
+---------------+---------------+
                |
                | shared API contract
                v
+-------------------------------+
| Task 3: Meeting to Scope      |
| - read transcript             |
| - extract requirements        |
| - check feasibility           |
| - estimate + draft proposal   |
| - approval gate               |
+-------------------------------+
```

## Task responsibilities

### Task 1 — Knowledge Brain

This is the shared service. It receives questions, searches indexed evidence, returns grounded answers, and creates escalation records when evidence is missing. The API contract is the integration boundary for downstream clients.

### Task 2 — Inbox Agent

This task reviews emails, classifies risk and intent, queries the Knowledge Brain for supporting evidence, drafts a response, and holds the draft for a human review step. The workflow is intentionally fail-closed: no refund, promise, or commitment is allowed without human approval.

### Task 3 — Meeting to Scope

This task converts transcript notes into requirements, scope, estimates, and a proposal. It also checks whether a request is already supported in the product knowledge base, which helps distinguish configuration work from custom development.

## Design choices

### Language split

We used Python for the API and orchestration-heavy tasks and TypeScript for the inbox client. This is a practical split: Python is comfortable for retrieval, validation, and service endpoints; TypeScript is suited to a typed client workflow with review logic.

### Prompt and output structure

The system uses versioned prompts, structured outputs, retries, and explicit review states. That makes failure modes visible and keeps the workflow auditable.

### Human-in-the-loop controls

The project uses explicit human review for the risky cases: unsupported commitments, large scope changes, and unanswered product questions. This is important for safety and keeps the system honest about uncertainty.

## Model choices

The architectural requirement points to Claude as the central model family. The repo is designed so that prompts and model selection can be compared using the same test cases. In this repository, the implemented validation is local and deterministic; the live model evaluation remains a future step rather than a claim of production performance.

## Deferred features

The project deliberately defers several things to keep the scope realistic:

- full production deployment
- continuous external knowledge ingestion at scale
- corporate secret management and encryption
- live Anthropic model benchmarking across multiple model families
- a polished commercial dashboard

These are the right trade-offs for a capstone build that must remain reviewable, testable, and honest.

## Limitations and next steps

The current build is a working local baseline, not a production service. The main gaps are:

- no live external product docs were indexed for a production knowledge base
- no real model comparison was run against external endpoints
- no end-user deployment or monitoring stack was added

The immediate next steps are:

1. expand the retrieval test set with real-world product content
2. compare Claude with a second model on the same cases
3. measure cost, latency, failure rate, and safety
4. keep the shared Knowledge Brain as the single integration point
