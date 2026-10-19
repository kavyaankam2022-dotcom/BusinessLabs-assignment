# Task 2 — Inbox Agent

The Inbox Agent classifies synthetic support emails, calls the Task 1 Knowledge Brain API, prepares evidence-backed Claude drafts, and keeps all customer-facing actions behind human review.

## Run locally

Requirements: Node.js 20 or later and the Task 1 API running at `http://127.0.0.1:8000`.

```powershell
npm install
npm run build
npm start
```

Open `http://127.0.0.1:3002`. For development, run `npm run build` after changing `src/ui.ts`, then `npm run dev`.

Set `KB_API_URL` if Task 1 uses another address. If the Knowledge Brain has `KB_API_KEY` configured, set the same key in the Inbox Agent process. Set `ANTHROPIC_API_KEY` and optionally `ANTHROPIC_MODEL` to enable drafting. Without a key, the system reports model unavailability and does not create a fallback customer reply. `INBOX_PORT` changes the local port; `INBOX_KB_TIMEOUT_MS` sets the Knowledge Brain timeout. `INBOX_STATE_PATH` changes the JSON interaction store path.

## Dataset and categories

`data/emails.json` contains 70 synthetic development emails. `data/holdout-emails.json` contains 20 separate final-test emails. Records contain expected category, risk, key facts, and expected behavior for evaluations; holdout answers are not loaded by the application, exposed by its API, or passed to the model.

The deterministic baseline identifies `how_to`, `troubleshooting`, `project_request`, `refund_cancellation`, `complaint`, `quote_request`, and `follow_up`, and assigns risk and urgency. Replace or compare this baseline with a model classifier only through measured evaluations.

## Review workflow

Select a message, generate its draft, inspect its category/risk and Knowledge Brain sources, edit as needed, then approve and simulate sending, reject with a replacement, or route to an expert. Simulated sends are idempotent and audited. No email provider is connected; the demo never delivers real messages. The service binds to loopback for local use and is not production-authenticated.

Interaction records retain the input email, retrieved evidence, draft, model/prompt versions, outcome, corrections, final sent text, and send ID. State is atomically saved to `.inbox-state/state.json` by default; keep real customer data out of this demo store.

The 20-consecutive rule compares normalized final text with the proposed draft exactly. Edits, rejection, expert escalation, high-risk cases, and non-ready outcomes reset the category streak. Only how-to and non-urgent troubleshooting categories can become eligible after 20 unchanged sends. Eligibility does not send automatically; a separate environment flag is required to enable the controlled trial, and human approval remains the only implemented send path.

## Tests

```powershell
npm run check
npm test
```

The tests validate the untouched 20-case classification holdout, Knowledge Brain success/failure behavior, unsafe commitment detection, review state, and simulated-send safeguards. Draft generation quality, model comparison, latency, and cost still require live model evaluations and are not claimed by the current test suite.
