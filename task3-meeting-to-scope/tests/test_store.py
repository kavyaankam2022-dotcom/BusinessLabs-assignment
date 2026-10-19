from datetime import date

from app.models import (
    ChangeReport,
    EstimateSummary,
    MeetingCreate,
    ProjectCreate,
    ProjectRevision,
    ProposalDocument,
    ScopeDocument,
    TranscriptAnalysis,
)
from app.store import ScopeStore


def make_revision(project_id: str, meeting_id: str, revision_number: int) -> ProjectRevision:
    return ProjectRevision(
        revision_id=f"revision-{revision_number}",
        project_id=project_id,
        meeting_id=meeting_id,
        revision_number=revision_number,
        status="pending_review",
        analysis=TranscriptAnalysis(),
        scope=ScopeDocument(objective="Website improvements", current_problem="Search is difficult.",
                            agreed_requirements=[], proposed_solution=[], deliverables=[], exclusions=[],
                            assumptions=[], dependencies=[], acceptance_criteria=[], client_responsibilities=[],
                            open_questions_and_risks=[]),
        estimate=EstimateSummary(),
        proposal=ProposalDocument(executive_summary="Draft", client_problem="Search is difficult.",
                                  proposed_solution=[], scope_and_deliverables=[], effort_summary="0-0 h",
                                  timeline_note="No date committed.", pricing_assumptions=[], client_responsibilities=[],
                                  exclusions_and_dependencies=[], risks_and_open_questions=[], approval_next_steps=[]),
        change_report=ChangeReport(),
    )


def test_pending_revision_is_not_baseline_until_human_approval(tmp_path):
    store = ScopeStore(str(tmp_path / "scope.db"))
    store.initialize()
    project_id = store.create_project(
        ProjectCreate(title="Website improvements", meeting_date=date(2026, 10, 1),
                      transcript="Client: We need to improve search before the campaign.", consent_confirmed=True),
        "meeting-1",
    )
    first = make_revision(project_id, "meeting-1", 1)
    store.create_revision(first)

    assert store.latest_approved_revision(project_id) is None
    assert store.review_revision(first.revision_id, "reviewer@example.test", "approve", "Baseline approved.")
    assert store.latest_approved_revision(project_id).revision_id == first.revision_id
    assert store.review_history(first.revision_id)[0]["reviewed_by"] == "reviewer@example.test"


def test_changes_requested_revision_does_not_replace_approved_baseline(tmp_path):
    store = ScopeStore(str(tmp_path / "scope.db"))
    store.initialize()
    request = ProjectCreate(title="Website improvements", meeting_date=date(2026, 10, 1),
                            transcript="Client: We need to improve search before the campaign.", consent_confirmed=True)
    project_id = store.create_project(request, "meeting-1")
    baseline = make_revision(project_id, "meeting-1", 1)
    store.create_revision(baseline)
    store.review_revision(baseline.revision_id, "reviewer", "approve", "Approved baseline.")
    assert store.add_meeting(project_id, "meeting-2", MeetingCreate(
        meeting_date=date(2026, 10, 8), transcript="Client: Add a location filter.", consent_confirmed=True,
    ))
    followup = make_revision(project_id, "meeting-2", store.next_revision_number(project_id))
    store.create_revision(followup)

    assert store.latest_approved_revision(project_id).revision_id == baseline.revision_id
    assert store.review_revision(followup.revision_id, "reviewer", "request_changes", "Clarify estimate." )
    assert store.latest_approved_revision(project_id).revision_id == baseline.revision_id
    assert [meeting["meeting_id"] for meeting in store.list_meetings(project_id)] == ["meeting-1", "meeting-2"]
