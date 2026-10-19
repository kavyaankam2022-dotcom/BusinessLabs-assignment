import uuid
from datetime import datetime, timezone

from .change_detector import ScopeChangeDetector
from .estimation_agent import EstimationAgent
from .feasibility_agent import ProductFeasibilityAgent
from .models import ProjectRevision
from .proposal_agent import ProposalReviewAgent
from .scope_agent import ScopeAgent
from .store import ScopeStore
from .transcript_analyst import TranscriptAnalyst


class MeetingToScopePipeline:
    def __init__(self, store: ScopeStore, analyst: TranscriptAnalyst | None = None,
                 feasibility_agent: ProductFeasibilityAgent | None = None) -> None:
        self.store = store
        self.analyst = analyst or TranscriptAnalyst()
        self.feasibility_agent = feasibility_agent or ProductFeasibilityAgent()
        self.change_detector = ScopeChangeDetector()
        self.scope_agent = ScopeAgent()
        self.estimation_agent = EstimationAgent()
        self.proposal_agent = ProposalReviewAgent()

    async def process(self, project_id: str, project_title: str, meeting_id: str,
                      transcript: str, revision_number: int) -> ProjectRevision:
        analysis = await self.analyst.analyze(meeting_id, transcript)
        requirements = await self.feasibility_agent.assess_all(analysis.requirements)
        analysis.requirements = requirements
        baseline = self.store.latest_approved_revision(project_id)
        change_report = self.change_detector.compare(baseline, analysis, meeting_id)
        scope = self.scope_agent.build(project_title, analysis, requirements)
        estimate = self.estimation_agent.estimate(requirements)
        proposal = self.proposal_agent.build(scope, estimate)
        return ProjectRevision(
            revision_id=str(uuid.uuid4()),
            project_id=project_id,
            meeting_id=meeting_id,
            revision_number=revision_number,
            status="pending_review",
            created_at=datetime.now(timezone.utc),
            analysis=analysis,
            scope=scope,
            estimate=estimate,
            proposal=proposal,
            change_report=change_report,
        )
