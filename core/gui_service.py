from __future__ import annotations

import threading
import re
from dataclasses import dataclass
from pathlib import Path

from .forms import build_card_forms
from .importer import build_database, load_database, update_database_source, write_database
from .manual_registry import (
    DisabledAutoFormRow,
    ManualAliasRow,
    ManualFormRow,
    ManualRegistry,
    load_manual_registry,
    save_manual_registry,
)
from .marker import annotate_match_result
from .matcher import LegalMatcher
from .models import AnnotationResult, EntityMatch, LegalEntity, MatchResult
from .normalizer import normalize_text


TEXT_EDIT_ACTIONS: tuple[tuple[str, str], ...] = (
    ("Вырезать", "<<Cut>>"),
    ("Копировать", "<<Copy>>"),
    ("Вставить", "<<Paste>>"),
    ("Выделить всё", "<<SelectAll>>"),
)


SHORTCUT_EVENTS_BY_KEYSYM: dict[str, str] = {
    "c": "<<Copy>>",
    "с": "<<Copy>>",
    "v": "<<Paste>>",
    "м": "<<Paste>>",
    "x": "<<Cut>>",
    "ч": "<<Cut>>",
    "a": "<<SelectAll>>",
    "ф": "<<SelectAll>>",
}

SHORTCUT_EVENTS_BY_KEYCODE: dict[int, str] = {
    67: "<<Copy>>",
    86: "<<Paste>>",
    88: "<<Cut>>",
    65: "<<SelectAll>>",
}


@dataclass(frozen=True)
class MarkedTextResult:
    marked_text: str
    match_count: int
    ambiguous_count: int
    annotation: AnnotationResult


@dataclass(frozen=True)
class SaveResult:
    path: Path
    text: str

    def write(self) -> None:
        self.path.write_text(self.text, encoding="utf-8")


@dataclass(frozen=True)
class ValidationCandidate:
    candidate_id: str
    group_id: str
    text: str
    start: int
    end: int
    entity: LegalEntity
    confidence: float
    match_type: str
    reason: str
    selected_by_default: bool
    is_ambiguous: bool

    def to_match(self) -> EntityMatch:
        return EntityMatch(
            entity=self.entity,
            start=self.start,
            end=self.end,
            text=self.text,
            confidence=self.confidence,
            match_type=self.match_type,
        )


@dataclass(frozen=True)
class ValidationResult:
    text: str
    candidates: tuple[ValidationCandidate, ...]
    match_count: int
    ambiguous_count: int


@dataclass(frozen=True)
class ValidationListRow:
    candidate_id: str
    label: str
    selected: bool
    is_ambiguous: bool


@dataclass(frozen=True)
class PaginatedValidationRows:
    rows: tuple[ValidationListRow, ...]
    page: int
    page_size: int
    total_pages: int
    total_rows: int


@dataclass(frozen=True)
class SourceUpdateOption:
    label: str
    source: str
    filetypes: tuple[tuple[str, str], ...]


@dataclass(frozen=True)
class MarkdownStyleRange:
    start: int
    end: int
    tag: str


@dataclass(frozen=True)
class LinkRange:
    start: int
    end: int
    url: str


@dataclass(frozen=True)
class CandidateDetailsText:
    text: str
    links: tuple[LinkRange, ...]


@dataclass(frozen=True)
class RegistryCardSummary:
    card_id: str
    canonical_name: str
    entity_type: str
    statuses: tuple[str, ...]
    source: str
    notes: str
    is_active: bool


@dataclass(frozen=True)
class RegistryCardState:
    card_id: str
    canonical_name: str
    entity_type: str
    statuses: tuple[str, ...]
    combined_status: str
    source: str
    notes: str
    official_aliases: tuple[str, ...]
    manual_aliases: tuple[str, ...]
    auto_forms: tuple[str, ...]
    manual_forms: tuple[str, ...]
    disabled_auto_forms: tuple[str, ...]
    active_forms: tuple[str, ...]


SOURCE_UPDATE_OPTIONS: tuple[SourceUpdateOption, ...] = (
    SourceUpdateOption(
        label="Иноагенты",
        source="foreign_agents",
        filetypes=(("Excel files", "*.xlsx"), ("All files", "*.*")),
    ),
    SourceUpdateOption(
        label="Нежелательные организации",
        source="undesirable_organizations",
        filetypes=(("Excel files", "*.xlsx"), ("All files", "*.*")),
    ),
    SourceUpdateOption(
        label="Росфинмониторинг: террористы и экстремисты",
        source="rosfinmonitoring",
        filetypes=(("Rosfinmonitoring files", "*.xls *.xlsx *.docx *.html *.htm"), ("All files", "*.*")),
    ),
    SourceUpdateOption(
        label="Экстремистские материалы",
        source="extremist_materials",
        filetypes=(("Registry files", "*.docx *.xls *.xlsx"), ("All files", "*.*")),
    ),
)


class MarkerService:
    def __init__(self, data_dir: Path | None = None, entities: list[LegalEntity] | None = None) -> None:
        self.data_dir = data_dir
        self._entities = entities
        self._matcher: LegalMatcher | None = None
        self._matcher_lock = threading.Lock()

    def mark_text(self, text: str) -> MarkedTextResult:
        if not text.strip():
            raise ValueError("Введите текст для маркировки.")
        annotation = annotate_match_result(text, self.matcher.match(text))
        return MarkedTextResult(
            marked_text=annotation.marked_text,
            match_count=len(annotation.matches),
            ambiguous_count=len(annotation.ambiguous_matches),
            annotation=annotation,
        )

    def analyze_text(self, text: str) -> ValidationResult:
        if not text.strip():
            raise ValueError("Введите текст для маркировки.")
        return validation_result_from_match_result(text, self.matcher.match(text))

    def apply_validation(self, analysis: ValidationResult, selected_candidate_ids: set[str]) -> MarkedTextResult:
        selected_matches = selected_matches_from_candidates(analysis.candidates, selected_candidate_ids)
        annotation = annotate_match_result(analysis.text, MatchResult(matches=selected_matches, ambiguous_matches=[]))
        return MarkedTextResult(
            marked_text=annotation.marked_text,
            match_count=len(annotation.matches),
            ambiguous_count=len(annotation.ambiguous_matches),
            annotation=annotation,
        )

    def reload(self) -> None:
        self._entities = None
        self._matcher = None

    def prepare_matcher(self) -> LegalMatcher:
        return self.matcher

    @property
    def is_matcher_ready(self) -> bool:
        return self._matcher is not None

    @property
    def entities(self) -> list[LegalEntity]:
        return self._ensure_loaded()

    @property
    def matcher(self) -> LegalMatcher:
        if self._matcher is None:
            with self._matcher_lock:
                if self._matcher is None:
                    self._matcher = LegalMatcher(self.entities)
        return self._matcher

    def _ensure_loaded(self) -> list[LegalEntity]:
        if self._entities is None:
            if self.data_dir is None:
                raise ValueError("Не указана папка с базой данных.")
            self._entities = load_database(self.data_dir)
        return self._entities


class RegistryEditorService:
    def __init__(self, data_dir: Path) -> None:
        self.data_dir = data_dir

    def list_cards(self, query: str = "", require_query: bool = False) -> tuple[RegistryCardSummary, ...]:
        registry = load_manual_registry(self._registry_path)
        entities_by_id = {entity.id: entity for entity in load_database(self.data_dir)}
        normalized_query = normalize_text(query)
        if require_query and not normalized_query:
            return ()
        cards: list[RegistryCardSummary] = []
        for row in registry.cards:
            entity = entities_by_id.get(row.card_id)
            statuses = entity.statuses if entity is not None else _split_registry_values(row.official_statuses)
            source = entity.source if entity is not None else row.source_keys
            summary = RegistryCardSummary(
                card_id=row.card_id,
                canonical_name=row.canonical_name,
                entity_type=row.entity_type,
                statuses=statuses,
                source=source,
                notes=row.notes,
                is_active=row.is_active != "0",
            )
            if normalized_query and normalized_query not in _summary_search_text(summary, registry):
                continue
            cards.append(summary)
        return tuple(cards)

    def get_card_state(self, card_id: str) -> RegistryCardState:
        registry = load_manual_registry(self._registry_path)
        entity = self._entity_by_id(card_id)
        card_row = next((row for row in registry.cards if row.card_id == card_id), None)
        if entity is None or card_row is None:
            raise ValueError(f"Карточка не найдена: {card_id}")
        manual_aliases = tuple(
            dict.fromkeys(row.alias.strip() for row in registry.manual_aliases if row.card_id == card_id and row.alias.strip())
        )
        manual_forms = tuple(
            dict.fromkeys(row.form.strip() for row in registry.manual_forms if row.card_id == card_id and row.form.strip())
        )
        disabled_auto_forms = tuple(
            dict.fromkeys(row.form.strip() for row in registry.disabled_auto_forms if row.card_id == card_id and row.form.strip())
        )
        auto_forms = tuple(
            form.text
            for form in build_card_forms(entity, manual_aliases=(), manual_forms=(), disabled_auto_forms=disabled_auto_forms)
        )
        active_forms = tuple(
            form.text
            for form in build_card_forms(
                entity,
                manual_aliases=manual_aliases,
                manual_forms=manual_forms,
                disabled_auto_forms=disabled_auto_forms,
            )
        )
        return RegistryCardState(
            card_id=card_id,
            canonical_name=card_row.canonical_name,
            entity_type=card_row.entity_type,
            statuses=entity.statuses,
            combined_status=entity.combined_status,
            source=entity.source,
            notes=card_row.notes,
            official_aliases=entity.aliases,
            manual_aliases=manual_aliases,
            auto_forms=auto_forms,
            manual_forms=manual_forms,
            disabled_auto_forms=disabled_auto_forms,
            active_forms=active_forms,
        )

    def add_manual_form(self, card_id: str, form: str, base_surface: str = "") -> RegistryCardState:
        cleaned = _clean_registry_value(form)
        if not cleaned:
            raise ValueError("Введите словоформу.")
        return self._mutate_registry(
            card_id,
            lambda registry, entity: _registry_with_manual_form_added(
                registry,
                entity,
                card_id,
                cleaned,
                base_surface or entity.name,
            ),
        )

    def remove_manual_form(self, card_id: str, form: str) -> RegistryCardState:
        cleaned = _clean_registry_value(form)
        return self._mutate_registry(card_id, lambda registry, _entity: _registry_with_manual_form_removed(registry, card_id, cleaned))

    def add_manual_alias(self, card_id: str, alias: str) -> RegistryCardState:
        cleaned = _clean_registry_value(alias)
        if not cleaned:
            raise ValueError("Введите алиас.")
        return self._mutate_registry(
            card_id,
            lambda registry, entity: _registry_with_manual_alias_added(registry, entity, card_id, cleaned),
        )

    def set_manual_aliases(self, card_id: str, aliases: tuple[str, ...] | list[str]) -> RegistryCardState:
        cleaned_aliases = tuple(
            dict.fromkeys(
                cleaned
                for cleaned in (_clean_registry_value(alias) for alias in aliases)
                if cleaned
            )
        )
        return self._mutate_registry(
            card_id,
            lambda registry, _entity: _registry_with_manual_aliases_replaced(registry, card_id, cleaned_aliases),
        )

    def remove_manual_alias(self, card_id: str, alias: str) -> RegistryCardState:
        cleaned = _clean_registry_value(alias)
        return self._mutate_registry(card_id, lambda registry, _entity: _registry_with_manual_alias_removed(registry, card_id, cleaned))

    def disable_auto_form(self, card_id: str, form: str, reason: str = "excluded_in_app") -> RegistryCardState:
        cleaned = _clean_registry_value(form)
        if not cleaned:
            raise ValueError("Выберите словоформу для исключения.")
        return self._mutate_registry(
            card_id,
            lambda registry, entity: _registry_with_disabled_form_added(registry, entity, card_id, cleaned, reason),
        )

    def restore_auto_form(self, card_id: str, form: str) -> RegistryCardState:
        cleaned = _clean_registry_value(form)
        return self._mutate_registry(card_id, lambda registry, _entity: _registry_with_disabled_form_removed(registry, card_id, cleaned))

    @property
    def _registry_path(self) -> Path:
        return self.data_dir / "manual_registry.xlsx"

    def _entity_by_id(self, card_id: str) -> LegalEntity | None:
        return next((entity for entity in load_database(self.data_dir) if entity.id == card_id), None)

    def _mutate_registry(self, card_id: str, update_fn) -> RegistryCardState:
        registry = load_manual_registry(self._registry_path)
        entity = self._entity_by_id(card_id)
        if entity is None:
            raise ValueError(f"Карточка не найдена: {card_id}")
        updated_registry = update_fn(registry, entity)
        save_manual_registry(self._registry_path, updated_registry)
        write_database(load_database(self.data_dir), self.data_dir, manual_registry=updated_registry)
        return self.get_card_state(card_id)


def update_database_from_sources(
    data_dir: Path,
    foreign_agents_path: Path,
    undesirable_path: Path,
    rosfinmonitoring_path: Path,
    extremist_materials_path: Path | None,
) -> int:
    entities = build_database(
        foreign_agents_path=foreign_agents_path,
        undesirable_path=undesirable_path,
        rosfinmonitoring_path=rosfinmonitoring_path,
        extremist_materials_path=extremist_materials_path,
        output_dir=data_dir,
    )
    return len(entities)


def validation_result_from_match_result(text: str, match_result: MatchResult) -> ValidationResult:
    candidates: list[ValidationCandidate] = []
    for index, match in enumerate(match_result.matches):
        candidates.append(
            ValidationCandidate(
                candidate_id=f"match:{index}",
                group_id=f"match:{index}",
                text=match.text,
                start=match.start,
                end=match.end,
                entity=match.entity,
                confidence=match.confidence,
                match_type=match.match_type,
                reason="",
                selected_by_default=True,
                is_ambiguous=False,
            )
        )
    for ambiguous_index, ambiguous_match in enumerate(match_result.ambiguous_matches):
        group_id = f"ambiguous:{ambiguous_index}:{ambiguous_match.start}:{ambiguous_match.end}"
        for candidate_index, entity in enumerate(ambiguous_match.candidates):
            candidates.append(
                ValidationCandidate(
                    candidate_id=f"{group_id}:{candidate_index}:{entity.id}",
                    group_id=group_id,
                    text=ambiguous_match.text,
                    start=ambiguous_match.start,
                    end=ambiguous_match.end,
                    entity=entity,
                    confidence=0.0,
                    match_type="ambiguous",
                    reason=ambiguous_match.reason,
                    selected_by_default=False,
                    is_ambiguous=True,
                )
            )
    return ValidationResult(
        text=text,
        candidates=tuple(candidates),
        match_count=len(match_result.matches),
        ambiguous_count=len(match_result.ambiguous_matches),
    )


def selected_matches_from_candidates(
    candidates: tuple[ValidationCandidate, ...],
    selected_candidate_ids: set[str],
) -> list[EntityMatch]:
    selected_matches: list[EntityMatch] = []
    occupied: list[tuple[int, int]] = []
    selected_candidates = [
        candidate
        for candidate in candidates
        if candidate.candidate_id in selected_candidate_ids
    ]
    for candidate in sorted(selected_candidates, key=lambda item: (item.start, -(item.end - item.start))):
        if _range_overlaps(candidate.start, candidate.end, occupied):
            continue
        selected_matches.append(candidate.to_match())
        occupied.append((candidate.start, candidate.end))
    return selected_matches


def _range_overlaps(start: int, end: int, ranges: list[tuple[int, int]]) -> bool:
    return any(start < existing_end and end > existing_start for existing_start, existing_end in ranges)


def default_selected_candidate_ids(candidates: tuple[ValidationCandidate, ...]) -> set[str]:
    return {
        candidate.candidate_id
        for candidate in candidates
        if candidate.selected_by_default
    }


def toggle_validation_candidate(
    candidates: tuple[ValidationCandidate, ...],
    selected_candidate_ids: set[str],
    target_candidate_id: str,
) -> set[str]:
    by_id = {candidate.candidate_id: candidate for candidate in candidates}
    candidate = by_id.get(target_candidate_id)
    if candidate is None:
        return set(selected_candidate_ids)

    updated = set(selected_candidate_ids)
    if target_candidate_id in updated:
        updated.remove(target_candidate_id)
        return updated

    updated.add(target_candidate_id)
    if candidate.is_ambiguous:
        for other in candidates:
            if other.group_id == candidate.group_id and other.candidate_id != candidate.candidate_id:
                updated.discard(other.candidate_id)
    return updated


def candidate_list_rows(
    candidates: tuple[ValidationCandidate, ...],
    selected_candidate_ids: set[str],
) -> tuple[ValidationListRow, ...]:
    return tuple(
        ValidationListRow(
            candidate_id=candidate.candidate_id,
            label=_candidate_list_label(candidate, candidate.candidate_id in selected_candidate_ids),
            selected=candidate.candidate_id in selected_candidate_ids,
            is_ambiguous=candidate.is_ambiguous,
        )
        for candidate in candidates
    )


def paginate_validation_rows(
    rows: tuple[ValidationListRow, ...],
    page: int,
    page_size: int,
) -> PaginatedValidationRows:
    safe_page_size = max(1, page_size)
    total_rows = len(rows)
    total_pages = max(1, (total_rows + safe_page_size - 1) // safe_page_size)
    safe_page = min(max(1, page), total_pages)
    start = (safe_page - 1) * safe_page_size
    end = start + safe_page_size
    return PaginatedValidationRows(
        rows=rows[start:end],
        page=safe_page,
        page_size=safe_page_size,
        total_pages=total_pages,
        total_rows=total_rows,
    )


def paginate_validation_candidates(
    candidates: tuple[ValidationCandidate, ...],
    selected_candidate_ids: set[str],
    page: int,
    page_size: int,
) -> PaginatedValidationRows:
    safe_page_size = max(1, page_size)
    total_rows = len(candidates)
    total_pages = max(1, (total_rows + safe_page_size - 1) // safe_page_size)
    safe_page = min(max(1, page), total_pages)
    start = (safe_page - 1) * safe_page_size
    end = start + safe_page_size
    page_candidates = candidates[start:end]
    rows = tuple(
        ValidationListRow(
            candidate_id=candidate.candidate_id,
            label=_candidate_list_label(candidate, candidate.candidate_id in selected_candidate_ids),
            selected=candidate.candidate_id in selected_candidate_ids,
            is_ambiguous=candidate.is_ambiguous,
        )
        for candidate in page_candidates
    )
    return PaginatedValidationRows(
        rows=rows,
        page=safe_page,
        page_size=safe_page_size,
        total_pages=total_pages,
        total_rows=total_rows,
    )


def source_update_options(include_all: bool = False) -> tuple[SourceUpdateOption, ...]:
    if not include_all:
        return SOURCE_UPDATE_OPTIONS
    return (
        SourceUpdateOption(
            label="Обновить всё",
            source="all_sources",
            filetypes=(),
        ),
        *SOURCE_UPDATE_OPTIONS,
    )


def update_database_source_from_file(data_dir: Path, source: str, source_path: Path) -> int:
    entities = update_database_source(source=source, source_path=source_path, output_dir=data_dir)
    return sum(entity.source != "builtins" for entity in entities)


def text_edit_actions() -> tuple[tuple[str, str], ...]:
    return TEXT_EDIT_ACTIONS


def shortcut_event_for_key(keysym: str, keycode: int | None = None) -> str | None:
    normalized_keysym = (keysym or "").lower()
    if normalized_keysym in SHORTCUT_EVENTS_BY_KEYSYM:
        return SHORTCUT_EVENTS_BY_KEYSYM[normalized_keysym]
    if keycode is not None:
        return SHORTCUT_EVENTS_BY_KEYCODE.get(keycode)
    return None


def candidate_details_text(candidate: ValidationCandidate) -> CandidateDetailsText:
    entity = candidate.entity
    aliases = ", ".join(entity.aliases) if entity.aliases else "нет"
    reason = candidate.reason or "нет"
    confidence = f"{candidate.confidence:.2f}" if candidate.confidence else "нет оценки"
    metadata_lines = _candidate_metadata_lines(entity.metadata)
    text = (
        f"Найдено в тексте: {candidate.text}\n"
        f"Позиция: {candidate.start}-{candidate.end}\n"
        f"Тип совпадения: {candidate.match_type}\n"
        f"Уверенность: {confidence}\n"
        f"Спорность: {reason}\n\n"
        f"Название карточки: {entity.name}\n"
        f"Тип карточки: {_entity_type_label(entity.entity_type)}\n"
        f"Статус: {entity.combined_status}\n"
        f"Источник: {entity.source or 'не указан'}\n"
        f"ID: {entity.id}\n\n"
        f"Алиасы:\n{aliases}\n\n"
        f"Дополнительные данные:\n"
    )
    links: list[LinkRange] = []
    resource_links = resource_links_from_metadata(entity.metadata)
    if resource_links:
        text += "Доменные имена информационного ресурса:\n"
        for link in resource_links:
            start = len(text)
            text += f"{link}\n"
            links.append(LinkRange(start=start, end=start + len(link), url=_clickable_url(link)))
        if metadata_lines:
            text += "\n"
    text += "\n".join(metadata_lines) if metadata_lines else ("нет" if not resource_links else "")
    return CandidateDetailsText(text=text.rstrip(), links=tuple(links))


def resource_links_from_metadata(metadata: dict[str, str]) -> tuple[str, ...]:
    links: list[str] = []
    for key, value in metadata.items():
        if _is_resource_domain_key(key):
            links.extend(_extract_links(str(value)))
    return tuple(dict.fromkeys(links))


def markdown_style_ranges(text: str) -> tuple[MarkdownStyleRange, ...]:
    ranges: list[MarkdownStyleRange] = []
    for match in re.finditer(r"(?<!_)_([^_\n]+?)_(?!_)", text):
        ranges.append(MarkdownStyleRange(match.start(), match.start() + 1, "markdown_hidden"))
        ranges.append(MarkdownStyleRange(match.start() + 1, match.end() - 1, "markdown_italic"))
        ranges.append(MarkdownStyleRange(match.end() - 1, match.end(), "markdown_hidden"))
    return tuple(sorted(ranges, key=lambda item: (item.start, item.end, item.tag)))


def _candidate_metadata_lines(metadata: dict[str, str]) -> list[str]:
    return [
        f"{key}: {value}"
        for key, value in sorted(metadata.items())
        if value not in ("", None) and not _is_resource_domain_key(key)
    ]


def _is_resource_domain_key(key: str) -> bool:
    normalized = re.sub(r"\s+", " ", key.casefold())
    return "доменное имя информационного ресурса" in normalized


def _extract_links(value: str) -> tuple[str, ...]:
    pattern = re.compile(
        r"(?:https?://)?(?:[A-Za-z0-9А-Яа-яЁё](?:[A-Za-z0-9А-Яа-яЁё-]{0,61}[A-Za-z0-9А-Яа-яЁё])?\.)+"
        r"[A-Za-zА-Яа-яЁё]{2,}(?:/[^\s,;]*)?",
        re.IGNORECASE,
    )
    links = []
    for match in pattern.finditer(value):
        links.append(match.group(0).strip(".,;:()[]{}\"'«»“”"))
    return tuple(dict.fromkeys(link for link in links if link))


def _clickable_url(value: str) -> str:
    if re.match(r"^https?://", value, re.IGNORECASE):
        return value
    return f"https://{value}"


def _entity_type_label(entity_type: str) -> str:
    labels = {
        "person": "человек",
        "organization": "организация",
        "material": "материал",
    }
    return labels.get(entity_type, entity_type or "не указан")


def _candidate_list_label(candidate: ValidationCandidate, selected: bool) -> str:
    state = "Убрать" if selected else "Добавить"
    kind = "спорное" if candidate.is_ambiguous else "уверенное"
    confidence = f"{candidate.confidence:.2f}" if candidate.confidence else "?"
    return f"{state} • {candidate.text} → {candidate.entity.name} • {kind} • {confidence}"


def _split_registry_values(value: str) -> tuple[str, ...]:
    return tuple(part.strip() for part in str(value).split(";") if part.strip())


def _summary_search_text(summary: RegistryCardSummary, registry: ManualRegistry) -> str:
    manual_aliases = [
        row.alias.strip()
        for row in registry.manual_aliases
        if row.card_id == summary.card_id and row.alias.strip()
    ]
    parts = (
        summary.canonical_name,
        summary.entity_type,
        summary.source,
        *summary.statuses,
        *manual_aliases,
    )
    return " ".join(normalize_text(part) for part in parts if part)


def _clean_registry_value(value: str) -> str:
    return re.sub(r"\s+", " ", str(value)).strip()


def _registry_with_manual_form_added(
    registry: ManualRegistry,
    entity: LegalEntity,
    card_id: str,
    form: str,
    base_surface: str,
) -> ManualRegistry:
    auto_forms = {
        normalize_text(item.text)
        for item in build_card_forms(
            entity,
            manual_aliases=(),
            manual_forms=(),
            disabled_auto_forms=tuple(
                row.form for row in registry.disabled_auto_forms if row.card_id == card_id and row.form.strip()
            ),
        )
    }
    if normalize_text(form) in auto_forms:
        raise ValueError("Эта словоформа уже создается автоматически.")
    existing_manual = {
        normalize_text(row.form)
        for row in registry.manual_forms
        if row.card_id == card_id and row.form.strip()
    }
    if normalize_text(form) in existing_manual:
        return registry
    rows = list(registry.manual_forms)
    rows.append(
        ManualFormRow(
            card_id=card_id,
            base_surface=_clean_registry_value(base_surface) or entity.name,
            form=form,
            form_type="manual",
            comment="",
        )
    )
    return ManualRegistry(
        cards=registry.cards,
        manual_aliases=registry.manual_aliases,
        manual_forms=tuple(rows),
        disabled_auto_forms=registry.disabled_auto_forms,
    )


def _registry_with_manual_form_removed(registry: ManualRegistry, card_id: str, form: str) -> ManualRegistry:
    normalized = normalize_text(form)
    rows = tuple(
        row
        for row in registry.manual_forms
        if not (row.card_id == card_id and normalize_text(row.form) == normalized)
    )
    return ManualRegistry(
        cards=registry.cards,
        manual_aliases=registry.manual_aliases,
        manual_forms=rows,
        disabled_auto_forms=registry.disabled_auto_forms,
    )


def _registry_with_manual_alias_added(
    registry: ManualRegistry,
    entity: LegalEntity,
    card_id: str,
    alias: str,
) -> ManualRegistry:
    auto_surfaces = {
        normalize_text(entity.name),
        *(normalize_text(item) for item in entity.aliases),
    }
    if normalize_text(alias) in auto_surfaces:
        raise ValueError("Этот алиас уже есть в карточке.")
    existing_manual = {
        normalize_text(row.alias)
        for row in registry.manual_aliases
        if row.card_id == card_id and row.alias.strip()
    }
    if normalize_text(alias) in existing_manual:
        return registry
    rows = list(registry.manual_aliases)
    rows.append(ManualAliasRow(card_id=card_id, alias=alias, alias_type="manual", comment=""))
    return ManualRegistry(
        cards=registry.cards,
        manual_aliases=tuple(rows),
        manual_forms=registry.manual_forms,
        disabled_auto_forms=registry.disabled_auto_forms,
    )


def _registry_with_manual_alias_removed(registry: ManualRegistry, card_id: str, alias: str) -> ManualRegistry:
    normalized = normalize_text(alias)
    rows = tuple(
        row
        for row in registry.manual_aliases
        if not (row.card_id == card_id and normalize_text(row.alias) == normalized)
    )
    return ManualRegistry(
        cards=registry.cards,
        manual_aliases=rows,
        manual_forms=registry.manual_forms,
        disabled_auto_forms=registry.disabled_auto_forms,
    )


def _registry_with_manual_aliases_replaced(
    registry: ManualRegistry,
    card_id: str,
    aliases: tuple[str, ...],
) -> ManualRegistry:
    preserved_rows = [
        row
        for row in registry.manual_aliases
        if row.card_id != card_id
    ]
    replaced_rows = [
        ManualAliasRow(card_id=card_id, alias=alias, alias_type="manual", comment="")
        for alias in aliases
    ]
    return ManualRegistry(
        cards=registry.cards,
        manual_aliases=tuple((*preserved_rows, *replaced_rows)),
        manual_forms=registry.manual_forms,
        disabled_auto_forms=registry.disabled_auto_forms,
    )


def _registry_with_disabled_form_added(
    registry: ManualRegistry,
    entity: LegalEntity,
    card_id: str,
    form: str,
    reason: str,
) -> ManualRegistry:
    auto_forms = {
        normalize_text(item.text)
        for item in build_card_forms(entity, manual_aliases=(), manual_forms=(), disabled_auto_forms=())
    }
    if normalize_text(form) not in auto_forms:
        raise ValueError("Можно исключать только автоматически созданные формы.")
    existing_disabled = {
        normalize_text(row.form)
        for row in registry.disabled_auto_forms
        if row.card_id == card_id and row.form.strip()
    }
    if normalize_text(form) in existing_disabled:
        return registry
    rows = list(registry.disabled_auto_forms)
    rows.append(DisabledAutoFormRow(card_id=card_id, form=form, reason=_clean_registry_value(reason)))
    return ManualRegistry(
        cards=registry.cards,
        manual_aliases=registry.manual_aliases,
        manual_forms=registry.manual_forms,
        disabled_auto_forms=tuple(rows),
    )


def _registry_with_disabled_form_removed(registry: ManualRegistry, card_id: str, form: str) -> ManualRegistry:
    normalized = normalize_text(form)
    rows = tuple(
        row
        for row in registry.disabled_auto_forms
        if not (row.card_id == card_id and normalize_text(row.form) == normalized)
    )
    return ManualRegistry(
        cards=registry.cards,
        manual_aliases=registry.manual_aliases,
        manual_forms=registry.manual_forms,
        disabled_auto_forms=rows,
    )
