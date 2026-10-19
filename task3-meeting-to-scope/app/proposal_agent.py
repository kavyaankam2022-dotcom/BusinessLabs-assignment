from .models import EstimateSummary, ProposalDocument, ScopeDocument


class ProposalReviewAgent:
    def build(self, scope: ScopeDocument, estimate: EstimateSummary) -> ProposalDocument:
        likely_range = f"{estimate.low_hours:g}-{estimate.high_hours:g} engineering hours"
        return ProposalDocument(
            executive_summary=(
                f"This draft outlines a reviewable approach for {scope.objective}. "
                "Requirements, feasibility, and assumptions remain subject to human approval."
            ),
            client_problem=scope.current_problem,
            proposed_solution=scope.proposed_solution,
            scope_and_deliverables=scope.deliverables,
            effort_summary=f"Planning range: {likely_range}; likely effort {estimate.likely_hours:g} hours.",
            timeline_note="No calendar delivery date is committed. A schedule requires approved scope, capacity, and dependency review.",
            pricing_assumptions=["No price is calculated or offered in this draft."],
            client_responsibilities=scope.client_responsibilities,
            exclusions_and_dependencies=scope.exclusions + scope.dependencies,
            risks_and_open_questions=scope.open_questions_and_risks + estimate.warnings,
            approval_next_steps=[
                "Resolve open questions and verify source evidence.",
                "Review the effort ranges and dependencies with a human estimator.",
                "Approve a revision before sharing it with the client.",
            ],
        )
