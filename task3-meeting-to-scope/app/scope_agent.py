from .models import Requirement, ScopeDocument, TranscriptAnalysis


class ScopeAgent:
    def build(self, project_title: str, analysis: TranscriptAnalysis,
              requirements: list[Requirement]) -> ScopeDocument:
        confirmed = [item for item in requirements if item.status == "confirmed"]
        unclear = [item for item in requirements if item.status != "confirmed"]
        deliverables = [
            f"Review and document the supported approach for: {item.description}"
            if item.feasibility.classification == "existing_configuration"
            else f"Provide a reviewed implementation plan for: {item.description}"
            for item in confirmed
        ]
        questions = list(analysis.open_questions)
        questions.extend(f"Confirm requirement and acceptance criteria: {item.description}" for item in unclear)
        questions.extend(
            f"Product feasibility needs human confirmation: {item.description} ({item.feasibility.rationale})"
            for item in requirements if item.feasibility.needs_human
        )
        return ScopeDocument(
            objective=project_title,
            current_problem=" ".join(item.details for item in confirmed[:3]) or "Needs client clarification.",
            agreed_requirements=confirmed,
            proposed_solution=deliverables,
            deliverables=deliverables,
            exclusions=[
                "Unconfirmed requirements are not included as delivery commitments.",
                "Custom development and third-party integrations are excluded until feasibility is approved.",
                "Pricing and delivery dates are not committed by this draft.",
            ],
            assumptions=list(analysis.assumptions),
            dependencies=list(dict.fromkeys(dependency for item in requirements for dependency in item.dependencies)),
            acceptance_criteria=list(dict.fromkeys(criterion for item in confirmed for criterion in item.acceptance_criteria)),
            client_responsibilities=[
                "Confirm unclear requirements and acceptance criteria.",
                "Provide required account access, sample data, and third-party documentation through approved channels.",
                "Review and approve the scope before work is scheduled.",
            ],
            open_questions_and_risks=list(dict.fromkeys(questions)),
        )
