# AI Coding Log

This log reflects the actual coding workflow used while building the project scaffold and submission materials. It notes both useful prompts and a decision to reject a poor architectural direction.

## Useful prompts used

### 1. "Create a repo structure for a three-part AI consulting capstone with task folders and the required submission docs."
Outcome: created the base project layout and file structure.

### 2. "Build a single launcher script that boots the shared API and the downstream tasks and checks health endpoints."
Outcome: produced `scripts/start_all.py` and the shared environment wiring.

### 3. "Add a minimal Knowledge Brain UI with visible states for success, failure, and unanswered questions."
Outcome: created the lightweight interface in `task1-knowledge-brain/web/`.

### 4. "Fix startup issues for Windows so the repo uses its local venv and local Node runtime instead of failing when PATH is incomplete."
Outcome: made the launcher robust for the actual local environment.

### 5. "Prepare concise submission docs that match the capstone brief and clearly separate measured results from pending live-model evaluation."
Outcome: updated the README, DESIGN, EVALS, and AI_LOG files.

## Rejected AI-generated direction

I rejected the idea of building one monolithic app for all three tasks. That would have hidden the required architecture boundary where Task 2 and Task 3 rely on the shared Knowledge Brain API. A single app would also make the evaluation, safety checks, and separate task ownership much less honest and much harder to review.

## Current note

This log records the actual work done in the repository. It does not claim live external model evaluation or production deployment beyond the measured local baseline and the validated startup sequence.
