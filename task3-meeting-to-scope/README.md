# Task 3 — Meeting to Scope

Task 3 converts consented meeting transcripts into traceable requirements, product feasibility checks, an explicit scope, low/likely/high hour ranges, and a proposal draft. Follow-up meetings are compared only with the latest human-approved revision.

## Run locally

From the repository root, install Task 3 dependencies and start the app:

```powershell
py -m pip install -r task3-meeting-to-scope/requirements.txt
py -m uvicorn app.server:app --app-dir task3-meeting-to-scope --host 127.0.0.1 --port 8002
```

Open `http://127.0.0.1:8002`. API documentation is at `/docs`. Set `SCOPE_DATABASE_PATH` to choose the SQLite file. Set `ANTHROPIC_API_KEY` and optionally `ANTHROPIC_MODEL` to enable Claude-assisted transcript extraction; without credentials, the deterministic extractor runs. Set `KB_API_URL` and optionally `KB_API_KEY` to connect to Task 1. Knowledge timeouts or insufficient evidence become `needs_clarification`, not a claim that the product lacks a feature.

## Workflow

1. Create a project with a meeting date, transcript, and explicit participant-consent confirmation.
2. Inspect requirements with source line, speaker, exact quote, status, priority, acceptance criteria, and dependencies.
3. Review Task 1 feasibility evidence and unresolved capability questions.
4. Inspect scope, task-hour ranges, assumptions, exclusions, and proposal draft.
5. Approve or request changes as a named reviewer. Only approved revisions become baselines.
6. Add a consented follow-up meeting to generate a revision and compare changes against that approved baseline.

The three role-played transcripts are in `transcripts/`. The 20 behavior cases are in `evaluation/cases.json` and exercised by pytest.

## Safety and limitations

- Transcripts are retained in SQLite with a SHA-256 digest; real meeting data requires appropriate consent and access controls.
- Claude-extracted requirements are accepted only if the quoted passage matches the original transcript. Deterministic extraction also preserves line citations.
- Estimate ranges are rule-based planning heuristics, not validated historical estimates, a quote, or a schedule. A human estimator must review them.
- There is no client-send integration. Revisions remain drafts until a named human approves them.
- Pending drafts and changes-requested revisions never replace the approved comparison baseline.
- The local demo binds to loopback and does not provide production authentication, multi-user access control, or encrypted storage.

## Tests

```powershell
py -m pytest task3-meeting-to-scope/tests -q
```
