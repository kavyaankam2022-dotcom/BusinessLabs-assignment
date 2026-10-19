import re

from .models import EstimateSummary, EstimateTask, Requirement


class EstimationAgent:
    def estimate(self, requirements: list[Requirement]) -> EstimateSummary:
        tasks: list[EstimateTask] = []
        warnings: list[str] = []
        for requirement in requirements:
            feasibility = requirement.feasibility.classification
            if feasibility == "needs_clarification":
                tasks.append(self._task(
                    requirement, "Feasibility investigation and requirements clarification",
                    1, 3, 6, "Implementation is not estimated until product support and requirements are confirmed.", "low",
                ))
                warnings.append(f"{requirement.requirement_id} is not implementation-estimated because feasibility is unclear.")
                continue

            factor = self._complexity_factor(requirement)
            if feasibility == "existing_configuration":
                tasks.append(self._task(requirement, "Configuration review and setup", 1 * factor, 2 * factor, 4 * factor,
                                        "Estimate assumes documented configuration meets the agreed acceptance criteria.", "medium"))
                tasks.append(self._task(requirement, "Configuration verification and handoff", 1, 2, 3,
                                        "Test against client-confirmed acceptance criteria.", "medium"))
            else:
                tasks.append(self._task(requirement, "Technical investigation and design", 2 * factor, 4 * factor, 8 * factor,
                                        "Human review must confirm product limitation and approach.", "low"))
                tasks.append(self._task(requirement, "Implementation and integration", 4 * factor, 8 * factor, 16 * factor,
                                        "Custom work estimate is provisional and excludes unverified third-party scope.", "low"))
                tasks.append(self._task(requirement, "Testing, acceptance, and deployment planning", 2 * factor, 4 * factor, 8 * factor,
                                        "Includes test planning; external approvals and vendor delays are not hours.", "low"))
                warnings.append(f"{requirement.requirement_id} requires technical approval before a quote or delivery commitment.")

        return EstimateSummary(
            tasks=tasks,
            low_hours=round(sum(task.low_hours for task in tasks), 1),
            likely_hours=round(sum(task.likely_hours for task in tasks), 1),
            high_hours=round(sum(task.high_hours for task in tasks), 1),
            assumptions=[
                "These are planning ranges, not a commercial quote or schedule commitment.",
                "Unclear requirements are limited to discovery; implementation effort is deferred.",
                "Third-party access, data quality, and client response times can change the range.",
            ],
            warnings=list(dict.fromkeys(warnings)),
        )

    @staticmethod
    def _complexity_factor(requirement: Requirement) -> float:
        text = requirement.description.casefold()
        if re.search(r"payment|migration|integrat|external api|inventory|checkout", text):
            return 2.0
        if re.search(r"search|filter|mobile|multi|notification|workflow", text):
            return 1.5
        return 1.0

    @staticmethod
    def _task(requirement: Requirement, name: str, low: float, likely: float, high: float,
              reasoning: str, confidence: str) -> EstimateTask:
        return EstimateTask(
            task_id=f"{requirement.requirement_id}-{len(name)}",
            requirement_id=requirement.requirement_id,
            name=name,
            reasoning=reasoning,
            low_hours=low,
            likely_hours=likely,
            high_hours=high,
            assumptions=["Re-estimate after scope and dependencies are reviewed."],
            dependencies=requirement.dependencies,
            confidence=confidence,  # type: ignore[arg-type]
        )
