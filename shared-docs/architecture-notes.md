# Shared architecture notes

This folder stores cross-project design notes, review artifacts, and shared assumptions.

## Key design principles

- one shared Knowledge Brain service
- all downstream tasks call the same API contract
- human approval required for risky output
- evidence and citations are mandatory
- metadata must be versioned and auditable

## Reusable patterns

- structured JSON responses
- typed API contracts
- versioned prompt records
- normalized source metadata
- evaluation datasets and model comparison logs
