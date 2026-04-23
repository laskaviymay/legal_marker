from __future__ import annotations

from .matcher import LegalMatcher
from .models import AnnotationResult, EntityMatch, LegalEntity, MatchResult


DISCLOSURE_TITLE = "Расшифровка маркировки"


def annotate_text(text: str, entities: list[LegalEntity]) -> AnnotationResult:
    return annotate_match_result(text, LegalMatcher(entities).match(text))


def annotate_match_result(text: str, match_result: MatchResult) -> AnnotationResult:
    marker_by_status = _assign_markers(match_result.matches)
    marked_body = _insert_markers(text, match_result.matches, marker_by_status)
    disclosure = _render_disclosure(match_result.matches, marker_by_status)
    marked_text = marked_body if not disclosure else f"{marked_body}\n\n{disclosure}"
    return AnnotationResult(
        marked_text=marked_text,
        matches=match_result.matches,
        ambiguous_matches=match_result.ambiguous_matches,
        marker_by_status=marker_by_status,
    )


def _assign_markers(matches: list[EntityMatch]) -> dict[str, str]:
    marker_by_status: dict[str, str] = {}
    for match in matches:
        status = match.entity.combined_status
        if status not in marker_by_status:
            marker_by_status[status] = "*" * (len(marker_by_status) + 1)
    return marker_by_status


def _insert_markers(text: str, matches: list[EntityMatch], marker_by_status: dict[str, str]) -> str:
    result = text
    for match in sorted(matches, key=lambda item: item.end, reverse=True):
        marker = marker_by_status[match.entity.combined_status]
        result = result[: match.end] + marker + result[match.end :]
    return result


def _render_disclosure(matches: list[EntityMatch], marker_by_status: dict[str, str]) -> str:
    seen: set[str] = set()
    lines: list[str] = []
    for match in matches:
        entity = match.entity
        if entity.id in seen:
            continue
        seen.add(entity.id)
        marker = marker_by_status[entity.combined_status]
        lines.append(f"_{marker} {entity.name} — {entity.combined_status}_")
    return "\n".join(lines)
