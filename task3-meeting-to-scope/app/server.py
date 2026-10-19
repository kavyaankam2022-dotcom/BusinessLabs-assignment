import os
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse

from .models import MeetingCreate, ProjectCreate, ProjectRevision, RevisionReview
from .pipeline import MeetingToScopePipeline
from .store import ScopeStore

store = ScopeStore()
pipeline = MeetingToScopePipeline(store)


@asynccontextmanager
async def lifespan(_app: FastAPI):
    store.initialize()
    yield


app = FastAPI(
    title="Meeting to Scope",
    version="1.0.0",
    description="Transcript analysis, feasibility, scope, estimates, proposal drafts, and approval history.",
    lifespan=lifespan,
)
WEB_ROOT = Path(__file__).resolve().parents[1] / "web"


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "service": "meeting-to-scope", "client_delivery": "disabled"}


@app.get("/")
def home() -> FileResponse:
    return FileResponse(WEB_ROOT / "index.html")


@app.get("/styles.css")
def styles() -> FileResponse:
    return FileResponse(WEB_ROOT / "styles.css", media_type="text/css")


@app.get("/ui.js")
def user_interface_script() -> FileResponse:
    return FileResponse(WEB_ROOT / "ui.js", media_type="text/javascript")


@app.get("/projects")
def list_projects() -> list[dict[str, object]]:
    return store.list_projects()


@app.post("/projects", response_model=ProjectRevision, status_code=201)
async def create_project(request: ProjectCreate) -> ProjectRevision:
    if not request.consent_confirmed:
        raise HTTPException(status_code=400, detail="Confirm consent before storing or analyzing a transcript.")
    meeting_id = _new_id()
    project_id = store.create_project(request, meeting_id)
    revision = await pipeline.process(
        project_id=project_id,
        project_title=request.title,
        meeting_id=meeting_id,
        transcript=request.transcript,
        revision_number=1,
    )
    store.create_revision(revision)
    return revision


@app.get("/projects/{project_id}/meetings")
def list_meetings(project_id: str) -> list[dict[str, object]]:
    if not store.project(project_id):
        raise HTTPException(status_code=404, detail="Project not found.")
    return store.list_meetings(project_id)


@app.get("/projects/{project_id}/meetings/{meeting_id}")
def get_meeting(project_id: str, meeting_id: str) -> dict[str, object]:
    meeting = store.meeting_transcript(meeting_id)
    if not meeting or meeting["project_id"] != project_id:
        raise HTTPException(status_code=404, detail="Meeting not found.")
    return meeting


@app.post("/projects/{project_id}/meetings", response_model=ProjectRevision, status_code=201)
async def add_followup_meeting(project_id: str, request: MeetingCreate) -> ProjectRevision:
    if not request.consent_confirmed:
        raise HTTPException(status_code=400, detail="Confirm consent before storing or analyzing a transcript.")
    project = store.project(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found.")
    meeting_id = _new_id()
    if not store.add_meeting(project_id, meeting_id, request):
        raise HTTPException(status_code=404, detail="Project not found.")
    revision = await pipeline.process(
        project_id=project_id,
        project_title=project["title"],
        meeting_id=meeting_id,
        transcript=request.transcript,
        revision_number=store.next_revision_number(project_id),
    )
    store.create_revision(revision)
    return revision


@app.get("/projects/{project_id}/revisions", response_model=list[ProjectRevision])
def list_revisions(project_id: str) -> list[ProjectRevision]:
    if not store.project(project_id):
        raise HTTPException(status_code=404, detail="Project not found.")
    return store.list_revisions(project_id)


@app.get("/projects/{project_id}/revisions/{revision_id}", response_model=ProjectRevision)
def get_revision(project_id: str, revision_id: str) -> ProjectRevision:
    revision = store.get_revision(revision_id)
    if not revision or revision.project_id != project_id:
        raise HTTPException(status_code=404, detail="Revision not found.")
    return revision


@app.get("/projects/{project_id}/revisions/{revision_id}/reviews")
def get_review_history(project_id: str, revision_id: str) -> list[dict[str, object]]:
    revision = store.get_revision(revision_id)
    if not revision or revision.project_id != project_id:
        raise HTTPException(status_code=404, detail="Revision not found.")
    return store.review_history(revision_id)


@app.post("/projects/{project_id}/revisions/{revision_id}/review", response_model=ProjectRevision)
def review_revision(project_id: str, revision_id: str, request: RevisionReview) -> ProjectRevision:
    revision = store.get_revision(revision_id)
    if not revision or revision.project_id != project_id:
        raise HTTPException(status_code=404, detail="Revision not found.")
    if not store.review_revision(revision_id, request.reviewed_by, request.decision, request.note):
        raise HTTPException(status_code=409, detail="Only a pending revision can be reviewed.")
    updated = store.get_revision(revision_id)
    assert updated is not None
    return updated


def _new_id() -> str:
    import uuid

    return str(uuid.uuid4())


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="127.0.0.1", port=int(os.getenv("SCOPE_PORT", "8002")))
