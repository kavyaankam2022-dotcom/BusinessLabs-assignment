# BusinessLabs Assignment

This repository contains a three-part AI consulting workspace built around a shared Knowledge Brain service:

- Task 1: Knowledge Brain API
- Task 2: Inbox Agent
- Task 3: Meeting-to-Scope tool

The design keeps the retrieval logic in one service and makes the downstream tasks call that API instead of duplicating the same knowledge layer.

## What is here

- `task1-knowledge-brain/` — shared product knowledge API, ingestion flow, evidence store, and query logic
- `task2-inbox-agent/` — inbox review workflow, classification, draft generation, and review gates
- `task3-meeting-to-scope/` — transcript intake, requirements extraction, feasibility checks, estimates, and proposal logic
- `scripts/start_all.py` — one-command launcher for the integrated stack
- `README.md`, `DESIGN.md`, `EVALS.md`, `AI_LOG.md` — submission documents

## Prerequisites

- Python 3.11+ with a virtual environment
- Node.js 20+ or later on PATH for the inbox agent
- Git
- Local environment variables only; no production secrets are committed to the repo

## Setup

From the repository root:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r task1-knowledge-brain\requirements.txt
python -m pip install -r task3-meeting-to-scope\requirements.txt
cd task2-inbox-agent
npm install
cd ..
```

If Node is installed but not on `PATH`, add its `bin` directory before running the inbox app. Example:

```powershell
$env:PATH = "C:\Users\pavan\AppData\Local\nodejs\node-v24.20.0-win-x64;$env:PATH"
```

## Run the integrated app

From the repo root:

```powershell
python scripts/start_all.py
```

This starts the three services and checks their health endpoints.

Expected local URLs:

- Knowledge Brain: http://127.0.0.1:8000/docs
- Meeting-to-Scope: http://127.0.0.1:8002/docs
- Inbox Agent: http://127.0.0.1:3002

## Run tests

```powershell
.\.venv\Scripts\python.exe -m pytest task1-knowledge-brain\tests -q
.\.venv\Scripts\python.exe -m pytest task3-meeting-to-scope\tests -q
cd task2-inbox-agent
npm test -- --run
```

## Current status

This project has a working local baseline for the implemented tasks and a shared service launcher. It is not a claim of production deployment or live-model benchmarking. The repo clearly separates the tasks and keeps failure states visible.
