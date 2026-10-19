from .knowledge_client import KnowledgeBrainClient
from .models import FeasibilityResult, Requirement


class ProductFeasibilityAgent:
    def __init__(self, knowledge_client: KnowledgeBrainClient | None = None) -> None:
        self.knowledge_client = knowledge_client or KnowledgeBrainClient()

    async def assess(self, requirement: Requirement) -> FeasibilityResult:
        lookup = await self.knowledge_client.query(
            f"For project feasibility, what documented Brilliant Directories features, settings, "
            f"integrations, or limitations apply to this client requirement? {requirement.description}"
        )
        if lookup.status != "answered" or lookup.needs_human or not lookup.sources:
            if lookup.error:
                rationale = lookup.error
            elif lookup.escalation_id:
                rationale = "Knowledge Brain escalated this capability question."
            else:
                rationale = "No source evidence resolves this requirement; absence of search results is not proof of missing functionality."
            return FeasibilityResult(
                classification="needs_clarification",
                rationale=rationale,
                sources=lookup.sources,
                needs_human=True,
            )

        text = " ".join([lookup.answer, *(str(source.get("excerpt", "")) for source in lookup.sources)]).casefold()
        if any(phrase in text for phrase in ("not supported", "not available", "cannot be configured", "does not support")):
            classification = "potential_custom_development"
            needs_human = True
            rationale = "Retrieved documentation describes a product limitation; confirm with a product expert before estimating custom work."
        elif any(word in text for word in ("limitation", "limited to", "only supports", "does not include")):
            classification = "existing_feature_with_limitation"
            needs_human = True
            rationale = "Documentation indicates an existing capability with a limitation that needs review against the requested behavior."
        elif any(word in text for word in ("setting", "configuration", "configure", "enable", "select")):
            classification = "existing_configuration"
            needs_human = False
            rationale = "Retrieved documentation describes a product configuration relevant to this requirement. Verify the exact fit with the client."
        else:
            classification = "needs_clarification"
            needs_human = True
            rationale = "Retrieved product information is related but does not establish whether the requirement is supported as requested."

        return FeasibilityResult(classification=classification, rationale=rationale, sources=lookup.sources, needs_human=needs_human)

    async def assess_all(self, requirements: list[Requirement]) -> list[Requirement]:
        assessed: list[Requirement] = []
        for requirement in requirements:
            requirement.feasibility = await self.assess(requirement)
            assessed.append(requirement)
        return assessed
