from difflib import SequenceMatcher
import re

from .models import ChangeItem, ChangeReport, ProjectRevision, Requirement, TranscriptAnalysis


class ScopeChangeDetector:
    def compare(self, baseline: ProjectRevision | None, current: TranscriptAnalysis,
                meeting_id: str) -> ChangeReport:
        if baseline is None or baseline.status != "approved":
            return ChangeReport(
                baseline_revision_id=None,
                items=[],
                summary="No approved baseline exists; this revision cannot be compared yet.",
            )

        original = baseline.analysis.requirements
        incoming = current.requirements
        items: list[ChangeItem] = []
        matched_baseline: set[str] = set()

        for requirement in incoming:
            if requirement.change_action == "add":
                items.append(ChangeItem(
                    kind="out_of_scope",
                    requirement_id=requirement.requirement_id,
                    description=requirement.description,
                    reason="The follow-up explicitly adds this request beyond the approved baseline; confirm scope and estimate separately.",
                    source_references=requirement.source_references,
                ))
                continue
            match = self._match(requirement, original, matched_baseline)
            if requirement.change_action == "remove":
                if match:
                    matched_baseline.add(match.requirement_id)
                    items.append(ChangeItem(
                        kind="removed",
                        requirement_id=match.requirement_id,
                        description=match.description,
                        reason="The follow-up meeting explicitly requested removal of this baseline item.",
                        source_references=requirement.source_references,
                    ))
                else:
                    items.append(ChangeItem(
                        kind="unresolved",
                        requirement_id=requirement.requirement_id,
                        description=requirement.description,
                        reason="A removal was requested but no matching approved-baseline requirement was identified.",
                        source_references=requirement.source_references,
                    ))
                continue

            if match:
                matched_baseline.add(match.requirement_id)
                if requirement.change_action == "modify" or _normalized(match.description) != _normalized(requirement.description):
                    items.append(ChangeItem(
                        kind="modified",
                        requirement_id=match.requirement_id,
                        description=f"Baseline: {match.description}\nFollow-up: {requirement.description}",
                        reason="The follow-up statement matches an approved requirement but changes its requested behavior.",
                        source_references=requirement.source_references,
                    ))
                continue

            if requirement.change_action in {"add", "none"}:
                items.append(ChangeItem(
                    kind="out_of_scope",
                    requirement_id=requirement.requirement_id,
                    description=requirement.description,
                    reason="This request is absent from the approved baseline and requires clarification and separate scope approval.",
                    source_references=requirement.source_references,
                ))

        items.extend(_constraint_changes(baseline, current))

        if not items:
            summary = "No changes to the approved baseline were identified from the extracted follow-up statements."
        else:
            counts: dict[str, int] = {}
            for item in items:
                counts[item.kind] = counts.get(item.kind, 0) + 1
            summary = ", ".join(f"{count} {kind}" for kind, count in sorted(counts.items())) + " compared with approved baseline."
        return ChangeReport(baseline_revision_id=baseline.revision_id, items=items, summary=summary)

    @staticmethod
    def _match(requirement: Requirement, baseline: list[Requirement], matched: set[str]) -> Requirement | None:
        by_id = next((item for item in baseline if item.requirement_id == requirement.requirement_id and item.requirement_id not in matched), None)
        if by_id:
            return by_id
        candidates = [item for item in baseline if item.requirement_id not in matched]
        if not candidates:
            return None
        ranked = sorted(
            candidates,
            key=lambda item: _match_score(requirement.description, item.description),
            reverse=True,
        )
        best = ranked[0]
        threshold = 0.42 if requirement.change_action in {"remove", "modify"} else 0.58
        return best if _match_score(requirement.description, best.description) >= threshold else None


def _normalized(value: str) -> str:
    return " ".join(value.casefold().split())


def _match_score(left: str, right: str) -> float:
    left_normalized, right_normalized = _normalized(left), _normalized(right)
    sequence_score = SequenceMatcher(None, left_normalized, right_normalized).ratio()
    left_terms, right_terms = set(left_normalized.split()), set(right_normalized.split())
    content_terms = {"search", "filter", "category", "location", "provider", "mobile", "date", "launch", "payment", "checkout", "notification", "integration"}
    left_content = left_terms & content_terms
    right_content = right_terms & content_terms
    overlap = len(left_content & right_content) / max(1, len(left_content | right_content))
    return max(sequence_score, overlap)


def _constraint_changes(baseline: ProjectRevision, current: TranscriptAnalysis) -> list[ChangeItem]:
    old_constraints = baseline.analysis.constraints
    new_constraints = current.constraints
    date_pattern = re.compile(
        r"\b(?:jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|jun(?:e)?|jul(?:y)?|"
        r"aug(?:ust)?|sep(?:tember)?|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?)\s+\d{1,2}\b|"
        r"\b\d{4}-\d{2}-\d{2}\b|\b\d{1,2}/\d{1,2}/\d{2,4}\b",
        re.IGNORECASE,
    )
    old_date_constraints = [item for item in old_constraints if date_pattern.search(item)]
    new_date_constraints = [item for item in new_constraints if date_pattern.search(item)]
    if not old_date_constraints or not new_date_constraints:
        return []
    old_text = old_date_constraints[-1]
    new_text = new_date_constraints[-1]
    old_dates = {match.group(0).casefold() for match in date_pattern.finditer(old_text)}
    new_dates = {match.group(0).casefold() for match in date_pattern.finditer(new_text)}
    if old_dates == new_dates:
        return []
    references = [
        reference for reference in current.constraint_references
        if reference.quote == new_text
    ]
    return [ChangeItem(
        kind="modified",
        description=f"Baseline constraint: {old_text}\nFollow-up constraint: {new_text}",
        reason="The follow-up changes a dated schedule constraint from the approved baseline; re-plan milestones before committing.",
        source_references=references,
    )]
