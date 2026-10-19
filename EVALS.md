# Evaluation Record

## Purpose

This file records the actual and planned evaluation work for the capstone. It distinguishes between measured local results and live-model cases that remain pending.

## Actual measured results

These results were run in this repository and are the current baseline:

| Task | Command | Result |
|---|---|---|
| Task 1 | `.\.venv\Scripts\python.exe -m pytest task1-knowledge-brain\tests -q` | 15 passed, 0 failed |
| Task 3 | `.\.venv\Scripts\python.exe -m pytest task3-meeting-to-scope\tests -q` | 29 passed, 0 failed |
| Task 2 | `cd task2-inbox-agent; npm test -- --run` | 35 passed, 0 failed |

The shared services were also started and health-checked successfully:

- Knowledge Brain: http://127.0.0.1:8000/health -> 200
- Meeting-to-Scope: http://127.0.0.1:8002/health -> 200
- Inbox Agent: http://127.0.0.1:3002/api/health -> 200

These are local deterministic results, not live model or production measurements.

## Evaluation method

For each task we used a fixed test dataset and consistent acceptance rules. The evaluation focuses on:

- correctness of the response
- grounding in available evidence
- refusal to invent unsupported answers
- safety and approval compliance
- latency and reliability where available

## Task 1 evaluation matrix

| Case ID | Type | Result |
|---|---|---|
| KB-001 | Direct fact lookup | Planned |
| KB-002 | Citation check | Planned |
| KB-003 | Multi-document answer | Planned |
| KB-004 | Screenshot evidence | Planned |
| KB-005 | Missing evidence refusal | Planned |
| KB-006 | Correct abstention | Planned |
| KB-007 | Updated article | Planned |
| KB-008 | Deleted article | Planned |
| KB-009 | Interrupt/resume ingestion | Planned |
| KB-010 | Timeout handling | Planned |
| KB-011 | Malformed request reject | Planned |
| KB-012 | Duplicate chunk reduction | Planned |
| KB-013 | Retrieval precision | Planned |
| KB-014 | Source traceability | Planned |
| KB-015 | Image-to-article linkage | Planned |
| KB-016 | Escalation record | Planned |
| KB-017 | Daily refresh | Planned |
| KB-018 | Failure isolation | Planned |
| KB-019 | API contract validation | Measured via local tests |
| KB-020 | Grounded answer contract | Measured via local tests |
| KB-021 | Missing evidence escalation | Measured via local tests |
| KB-022 | API validation fail case | Measured via local tests |

## Task 2 evaluation matrix

| Case ID | Type | Result |
|---|---|---|
| IN-001 | Development email classification | Measured |
| IN-002 | Holdout classification | Measured |
| IN-003 | Holdout classification | Measured |
| IN-004 | Holdout classification | Measured |
| IN-005 | Holdout classification | Measured |
| IN-006 | Holdout classification | Measured |
| IN-007 | Holdout classification | Measured |
| IN-008 | Holdout classification | Measured |
| IN-009 | Holdout classification | Measured |
| IN-010 | Holdout classification | Measured |
| IN-011 | Holdout classification | Measured |
| IN-012 | Holdout classification | Measured |
| IN-013 | Holdout classification | Measured |
| IN-014 | Holdout classification | Measured |
| IN-015 | Holdout classification | Measured |
| IN-016 | Holdout classification | Measured |
| IN-017 | Holdout classification | Measured |
| IN-018 | Holdout classification | Measured |
| IN-019 | Holdout classification | Measured |
| IN-020 | Holdout classification | Measured |
| IN-021 | Knowledge Brain client | Measured |
| IN-022 | Fail-closed safety | Measured |
| IN-023 | Draft approval flow | Measured |
| IN-024 | Review edit tracking | Measured |
| IN-025 | Autonomy gating | Measured |
| IN-026 | HTTP integration | Measured |

The full inbox suite passed locally: 35 passed, 0 failed. The synthetic holdout set was 20 cases, and all 20 matched expected labels in the deterministic rule-based classifier.

## Task 3 evaluation matrix

| Case ID | Type | Result |
|---|---|---|
| SC-001 | Transcript parsing | Measured via local tests |
| SC-002 | Consent gate | Measured via local tests |
| SC-003 | Requirement extraction | Measured via local tests |
| SC-004 | Scope revision logic | Measured via local tests |
| SC-005 | Approval path | Measured via local tests |
| SC-006 | Project persistence | Measured via local tests |
| SC-007 | Change detection | Planned |
| SC-008 | Out-of-scope detection | Planned |
| SC-009 | Feasibility check | Planned |
| SC-010 | Estimate range | Planned |
| SC-011 | Acceptance criteria | Planned |
| SC-012 | Proposal approval | Planned |
| SC-013 | Follow-up meeting diff | Planned |
| SC-014 | Risk and assumption tracking | Planned |
| SC-015 | Prompt consistency | Planned |
| SC-016 | Response grounding | Planned |
| SC-017 | Missing info flag | Planned |
| SC-018 | Product-config vs custom-dev | Planned |
| SC-019 | Safety gate | Planned |
| SC-020 | Unapproved send prevention | Planned |
| SC-021 | Human review requirement | Planned |
| SC-022 | Change comparison | Planned |
| SC-023 | Final proposal consistency | Planned |
| SC-024 | Estimation traceability | Planned |
| SC-025 | Transcript chunk quality | Planned |

## Reliability and safety note

The measurable local testing confirms the code paths for API validation, review rules, and deterministic scope logic work as expected. Live model quality, cost, and latency remain pending because no external Claude or alternate-model calls were performed in this run.

## Limitations

The repo is honest about what is and is not demonstrated:

- local tests passed for deterministic logic
- no external-model benchmarking was run
- no real costs or live latency numbers were captured on Anthropic or other services
- no real customer data or secrets were used
