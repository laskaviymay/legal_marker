from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from core.gui_service import (
    ValidationResult,
    default_selected_candidate_ids,
    selected_matches_from_candidates,
    validation_result_from_match_result,
)
from core.importer import load_database
from core.marker import annotate_match_result
from core.matcher import LegalMatcher
from core.models import LegalEntity, MatchResult


@dataclass(frozen=True)
class BotAnalyzeResult:
    analysis: ValidationResult | None
    marked_text: str | None


class BotRuntime:
    def __init__(self, data_dir: Path | None = None, entities: list[LegalEntity] | None = None) -> None:
        self._entities = list(entities) if entities is not None else None
        self._data_dir = data_dir
        self._matcher: LegalMatcher | None = None

    @property
    def entities(self) -> list[LegalEntity]:
        if self._entities is None:
            if self._data_dir is None:
                raise ValueError("BotRuntime requires data_dir or entities")
            self._entities = load_database(self._data_dir)
        return self._entities

    @property
    def matcher(self) -> LegalMatcher:
        if self._matcher is None:
            self._matcher = LegalMatcher(self.entities)
        return self._matcher

    def analyze(self, text: str) -> BotAnalyzeResult:
        validation = validation_result_from_match_result(text, self.matcher.match(text))
        has_ambiguous = any(candidate.is_ambiguous for candidate in validation.candidates)
        if has_ambiguous:
            return BotAnalyzeResult(analysis=validation, marked_text=None)
        selected_ids = default_selected_candidate_ids(validation.candidates)
        selected_matches = selected_matches_from_candidates(validation.candidates, selected_ids)
        annotation = annotate_match_result(text, MatchResult(matches=selected_matches, ambiguous_matches=[]))
        return BotAnalyzeResult(analysis=None, marked_text=annotation.marked_text)

    def apply(self, analysis: ValidationResult, selected_candidate_ids: set[str]) -> str:
        selected_matches = selected_matches_from_candidates(analysis.candidates, selected_candidate_ids)
        annotation = annotate_match_result(
            analysis.text,
            MatchResult(matches=selected_matches, ambiguous_matches=[]),
        )
        return annotation.marked_text

    def reload(self, data_dir: Path | None = None) -> None:
        if data_dir is not None:
            self._data_dir = data_dir
        self._entities = None
        self._matcher = None
