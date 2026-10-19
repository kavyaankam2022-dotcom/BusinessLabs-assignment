from datetime import date

from fastapi.testclient import TestClient

from app import server
from app.models import (
    ChangeReport,
    EstimateSummary,
    ProjectRevision,
    ProposalDocument,
    ScopeDocument,
    TranscriptAnalysis,
)
from app.store import ScopeStore


class StubPipeline:
    async def process(self, project_id, project_title, meeting_id, transcript, revision_number):
        return ProjectRevision(
            revision_id=f"revision-{revision_number}",
            project_id=project_id,
            meeting_id=meeting_id,
            revision_number=revision_number,
            status="pending_review",
            analysis=TranscriptAnalysis(),
            scope=ScopeDocument(objective=project_title, current_problem="Review pending.",
                                agreed_requirements=[], proposed_solution=[], deliverables=[], exclusions=[],
                                assumptions=[], dependencies=[], acceptance_criteria=[], client_responsibilities=[],
                                open_questions_and_risks=[]),
            estimate=EstimateSummary(),
            proposal=ProposalDocument(executive_summary="Draft proposal", client_problem="Review pending.",
                                      proposed_solution=[], scope_and_deliverables=[], effort_summary="0 hours",
                                      timeline_note="No timeline promised.", pricing_assumptions=[],
                                      client_responsibilities=[], exclusions_and_dependencies=[],
                                      risks_and_open_questions=[], approval_next_steps=[]),
            change_report=ChangeReport(),
        )


def test_transcript_requires_consent_and_revision_requires_approval(tmp_path, monkeypatch):
    store = ScopeStore(str(tmp_path / "api.db"))
    monkeypatch.setattr(server, "store", store)
    monkeypatch.setattr(server, "pipeline", StubPipeline())
    body = {
        "title": "Website search improvements",
        "meeting_date": "2026-10-01",
        "transcript": "Client: We need search filters before our winter campaign.",
        "consent_confirmed": False,
    }

    with TestClient(server.app) as client:
        refused = client.post("/projects", json=body)
        assert refused.status_code == 400
        assert "consent" in refused.json()["detail"].lower()

        body["consent_confirmed"] = True
        created = client.post("/projects", json=body)
        assert created.status_code == 201
        pending = created.json()
        assert pending["status"] == "pending_review"
        assert store.latest_approved_revision(pending["project_id"]) is None

        review = client.post(
            f"/projects/{pending['project_id']}/revisions/{pending['revision_id']}/review",
            json={"reviewed_by": "human-reviewer", "decision": "approve", "note": "Reviewed."},
        )
        assert review.status_code == 200
        assert review.json()["status"] == "approved"
        assert store.latest_approved_revision(pending["project_id"]).revision_id == pending["revision_id"]
