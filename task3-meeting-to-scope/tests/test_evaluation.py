import asyncio
import json
from pathlib import Path

import pytest

from app.change_detector import ScopeChangeDetector
from app.estimation_agent import EstimationAgent
from app.feasibility_agent import ProductFeasibilityAgent
from app.models import (
    ChangeReport,
    EstimateSummary,
    FeasibilityResult,
    KnowledgeQueryResult,
    ProjectRevision,
    ProposalDocument,
    Requirement,
    ScopeDocument,
    SourceReference,
    TranscriptAnalysis,
)
from app.proposal_agent import ProposalReviewAgent
from app.scope_agent import ScopeAgent
from app.transcript_analyst import TranscriptAnalyst, _requirement_id, analyze_deterministically, split_transcript

ROOT = Path(__file__).resolve().parents[1]


def requirement(description: str, *, action: str = "none", feasibility: str = "needs_clarification",
                status: str = "confirmed", requirement_id: str | None = None) -> Requirement:
    return Requirement(
        requirement_id=requirement_id or _requirement_id(description),
        description=description,
        details=description,
        status=status,
        priority="unknown",
        acceptance_criteria=["Client confirmation required: define a measurable acceptance criterion."],
        source_references=[SourceReference(meeting_id="meeting-test", line_start=1, line_end=1,
                                           speaker="Client", quote=description)],
        feasibility=FeasibilityResult(classification=feasibility),
        change_action=action,
    )


def revision(requirements: list[Requirement], status: str = "approved") -> ProjectRevision:
    return ProjectRevision(
        revision_id="revision-baseline",
        project_id="project-test",
        meeting_id="meeting-baseline",
        revision_number=1,
        status=status,
        analysis=TranscriptAnalysis(requirements=requirements),
        scope=ScopeDocument(objective="Test", current_problem="Test", agreed_requirements=requirements,
                            proposed_solution=[], deliverables=[], exclusions=[], assumptions=[], dependencies=[],
                            acceptance_criteria=[], client_responsibilities=[], open_questions_and_risks=[]),
        estimate=EstimateSummary(),
        proposal=ProposalDocument(executive_summary="", client_problem="", proposed_solution=[],
                                  scope_and_deliverables=[], effort_summary="", timeline_note="",
                                  pricing_assumptions=[], client_responsibilities=[], exclusions_and_dependencies=[],
                                  risks_and_open_questions=[], approval_next_steps=[]),
        change_report=ChangeReport(),
    )


def test_evaluation_matrix_has_twenty_cases():
    cases = json.loads((ROOT / "evaluation" / "cases.json").read_text(encoding="utf-8"))
    assert len(cases) == 20
    assert len({case["case_id"] for case in cases}) == 20


def test_extracts_client_requirement_with_exact_line_citation():
    analysis = analyze_deterministically("meeting-a", "[00:10] Client: We need a location filter for provider search.")
    item = analysis.requirements[0]
    assert item.source_references[0].line_start == 1
    assert item.source_references[0].speaker == "Client"
    assert item.source_references[0].quote == "We need a location filter for provider search."


def test_consultant_statements_are_not_misrepresented_as_client_requirements():
    analysis = analyze_deterministically("meeting-a", "\n".join([
        "Consultant: We will check the documented search settings.",
        "Client: We need a location filter for provider search.",
    ]))
    assert len(analysis.requirements) == 1
    assert analysis.requirements[0].source_references[0].speaker == "Client"


def test_vague_suggestion_stays_unclear():
    analysis = analyze_deterministically("meeting-a", "Client: Maybe add AI search when we know what that means.")
    assert analysis.requirements[0].status == "unclear"
    assert analysis.requirements[0].origin == "explicit"


def test_only_explicit_language_assigns_must_have_priority():
    analysis = analyze_deterministically("meeting-a", "Client: Category filter is required before launch.")
    assert analysis.requirements[0].priority == "must_have"


def test_chunks_long_transcript_with_overlapping_source_lines():
    transcript = "Client: requirement one\n" + "Client: long line " + ("x" * 9000) + "\nClient: final line"
    chunks = split_transcript(transcript, max_chars=1000, overlap_lines=1)
    assert len(chunks) > 3
    assert all(len(chunk.text) <= 1000 for chunk in chunks)
    long_line_chunks = [chunk for chunk in chunks if chunk.line_start == 2]
    assert len(long_line_chunks) > 1
    assert all(chunk.line_numbers[0] == 2 for chunk in long_line_chunks)


def test_preserves_decisions_constraints_and_open_questions():
    analysis = analyze_deterministically("meeting-a", "\n".join([
        "Consultant: What is the target date?",
        "Client: We agreed the launch target is November 30.",
        "Client: The deadline is November 30.",
    ]))
    assert analysis.decisions
    assert analysis.constraints
    assert analysis.open_questions


def test_conflicting_statements_are_disputed_not_silently_resolved():
    analysis = analyze_deterministically("meeting-conflict", "\n".join([
        "Client: We need a category filter on provider search.",
        "Client: We no longer need the category filter on provider search.",
    ]))
    assert all(item.status == "disputed" for item in analysis.requirements)
    assert any("Conflicting meeting statements" in question for question in analysis.open_questions)


def test_explicit_acceptance_language_is_retained():
    analysis = analyze_deterministically("meeting-a", "Client: Search must show only active providers.")
    assert any("only active providers" in item for item in analysis.requirements[0].acceptance_criteria)


def test_dependency_terms_become_explicit_dependencies():
    analysis = analyze_deterministically("meeting-b", "Client: We need to integrate the payment provider API.")
    assert analysis.requirements[0].dependencies


def test_sample_followup_has_add_remove_modify_and_uncertainty():
    transcript = (ROOT / "transcripts" / "meeting-c-search-followup.txt").read_text(encoding="utf-8")
    analysis = analyze_deterministically("meeting-c", transcript)
    actions = {item.change_action for item in analysis.requirements}
    assert "add" in actions
    assert "remove" in actions
    assert "modify" in actions
    assert any(item.status == "unclear" for item in analysis.requirements)


class FakeKnowledgeClient:
    def __init__(self, result: KnowledgeQueryResult):
        self.result = result
        self.questions: list[str] = []

    async def query(self, question: str) -> KnowledgeQueryResult:
        self.questions.append(question)
        return self.result


def test_feasibility_unavailable_is_needs_clarification_not_custom_work():
    client = FakeKnowledgeClient(KnowledgeQueryResult(status="unavailable", error="service down"))
    agent = ProductFeasibilityAgent(client)
    result = asyncio.run(agent.assess(requirement("Add a provider search filter")))
    assert result.classification == "needs_clarification"
    assert result.needs_human is True
    assert "service down" in result.rationale


def test_feasibility_requires_sources_before_existing_configuration():
    result = KnowledgeQueryResult(answer="Use the setting.", status="answered", sources=[], needs_human=False)
    assessed = asyncio.run(ProductFeasibilityAgent(FakeKnowledgeClient(result)).assess(requirement("Change search configuration")))
    assert assessed.classification == "needs_clarification"


def test_documented_setting_with_source_classifies_as_configuration():
    result = KnowledgeQueryResult(
        answer="Use the search settings page to configure category filters.",
        status="answered",
        sources=[{"title": "Search settings", "url": "https://support.example.test/search", "excerpt": "Configure filter settings."}],
        needs_human=False,
    )
    assessed = asyncio.run(ProductFeasibilityAgent(FakeKnowledgeClient(result)).assess(requirement("Configure search filters")))
    assert assessed.classification == "existing_configuration"
    assert assessed.needs_human is False


def test_no_search_evidence_never_proves_custom_development():
    result = KnowledgeQueryResult(status="insufficient_evidence", sources=[], needs_human=True)
    assessed = asyncio.run(ProductFeasibilityAgent(FakeKnowledgeClient(result)).assess(requirement("Add voice search")))
    assert assessed.classification != "potential_custom_development"


def test_scope_separates_confirmed_requirements_and_open_risks():
    confirmed = requirement("Add location filters", feasibility="existing_configuration")
    unclear = requirement("Maybe offer voice search", status="unclear")
    analysis = TranscriptAnalysis(requirements=[confirmed, unclear], open_questions=["Which languages?"])
    scope = ScopeAgent().build("Search update", analysis, [confirmed, unclear])
    assert [item.requirement_id for item in scope.agreed_requirements] == [confirmed.requirement_id]
    assert any("voice search" in item for item in scope.open_questions_and_risks)
    assert scope.exclusions
    assert scope.client_responsibilities


def test_unclear_requirement_gets_discovery_only_estimate():
    item = requirement("Add external payment provider", feasibility="needs_clarification")
    estimate = EstimationAgent().estimate([item])
    assert len(estimate.tasks) == 1
    assert "clarification" in estimate.tasks[0].name
    assert estimate.tasks[0].likely_hours == 3
    assert estimate.warnings


def test_all_estimate_ranges_are_ordered_and_summarized():
    items = [
        requirement("Configure search filters", feasibility="existing_configuration"),
        requirement("Integrate payment API", feasibility="potential_custom_development"),
    ]
    estimate = EstimationAgent().estimate(items)
    assert estimate.tasks
    assert all(task.low_hours <= task.likely_hours <= task.high_hours for task in estimate.tasks)
    assert estimate.low_hours <= estimate.likely_hours <= estimate.high_hours


def test_proposal_does_not_commit_price_or_calendar_date():
    scope = ScopeAgent().build("Commerce project", TranscriptAnalysis(), [])
    estimate = EstimateSummary(low_hours=4, likely_hours=7, high_hours=12)
    proposal = ProposalReviewAgent().build(scope, estimate)
    assert "No calendar delivery date is committed" in proposal.timeline_note
    assert proposal.pricing_assumptions == ["No price is calculated or offered in this draft."]


def test_followup_addition_is_flagged_out_of_scope():
    base = requirement("Configure existing search filters", feasibility="existing_configuration")
    added = requirement("Add voice search", action="add")
    report = ScopeChangeDetector().compare(revision([base]), TranscriptAnalysis(requirements=[added]), "meeting-followup")
    assert any(item.kind == "out_of_scope" and item.requirement_id == added.requirement_id for item in report.items)


def test_followup_modification_matches_approved_requirement():
    base = requirement("Filter provider search results by category", requirement_id="REQ-11111111")
    changed = requirement("Change provider search filters from category to location", action="modify", requirement_id="REQ-22222222")
    report = ScopeChangeDetector().compare(revision([base]), TranscriptAnalysis(requirements=[changed]), "meeting-followup")
    assert any(item.kind == "modified" for item in report.items)


def test_followup_removal_matches_approved_requirement():
    base = requirement("Filter provider search results by category", requirement_id="REQ-11111111")
    removed = requirement("Remove the category filter from provider search", action="remove", requirement_id="REQ-22222222")
    report = ScopeChangeDetector().compare(revision([base]), TranscriptAnalysis(requirements=[removed]), "meeting-followup")
    assert any(item.kind == "removed" for item in report.items)


def test_followup_target_date_change_is_reported_against_approved_baseline():
    baseline = revision([])
    baseline.analysis.constraints = ["Client: We hope to launch by November 30."]
    followup = analyze_deterministically("meeting-followup", "Client: Change the campaign target from November 30 to January 15.")
    report = ScopeChangeDetector().compare(baseline, followup, "meeting-followup")

    assert any(item.kind == "modified" and "January 15" in item.description for item in report.items)


def test_missing_requirement_in_followup_is_not_silently_removed():
    base = requirement("Filter provider search results by category")
    report = ScopeChangeDetector().compare(revision([base]), TranscriptAnalysis(requirements=[]), "meeting-followup")
    assert report.items == []


def test_pending_revision_cannot_be_used_as_approved_baseline():
    pending = revision([requirement("Original baseline requirement")], status="pending_review")
    report = ScopeChangeDetector().compare(pending, TranscriptAnalysis(requirements=[requirement("New request")]), "meeting-followup")
    assert report.baseline_revision_id is None
    assert "No approved baseline" in report.summary


def test_scope_comparison_only_points_to_approved_revision_id():
    approved = revision([requirement("Original requirement")], status="approved")
    report = ScopeChangeDetector().compare(approved, TranscriptAnalysis(requirements=[]), "meeting-followup")
    assert report.baseline_revision_id == approved.revision_id
