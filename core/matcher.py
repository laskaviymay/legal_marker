from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from typing import Any

from .models import AmbiguousMatch, EntityMatch, LegalEntity, MatchResult
from .normalizer import normalize_key, normalize_text, person_search_keys, phrase_pattern, significant_alias, tokenize

LOGGER = logging.getLogger(__name__)

ORG_CONTEXT_WORDS = {
    "ассоциация",
    "группа",
    "движение",
    "коалиция",
    "комитет",
    "компания",
    "комьюнити",
    "медиа",
    "объединение",
    "организация",
    "партия",
    "проект",
    "сообщество",
    "союз",
    "центр",
    "фонд",
    "foundation",
    "inc",
    "organization",
    "project",
}

WEAK_ALIAS_NEGATIVE_LEFT = {
    "в",
    "данное",
    "другое",
    "каждое",
    "любое",
    "совершил",
    "совершила",
    "такое",
    "это",
}


@dataclass(frozen=True)
class _Term:
    text: str
    kind: str
    entity: LegalEntity
    key: str


class LegalMatcher:
    def __init__(self, entities: list[LegalEntity]) -> None:
        self.entities = entities
        self._terms_by_key = self._build_terms(entities)
        self._candidate_keys_by_token = self._build_candidate_index(self._terms_by_key)
        self._ner = self._build_ner()

    def match(self, text: str) -> MatchResult:
        accepted: list[EntityMatch] = []
        ambiguous: list[AmbiguousMatch] = []
        occupied: list[tuple[int, int]] = []
        text_tokens = set(normalize_key(text).split())
        person_text_tokens = _person_search_tokens(text)
        ner_ranges = self._extract_ner_ranges(text)

        for key, terms in self._iter_candidate_terms_longest_first(text_tokens, person_text_tokens):
            is_person_term = any(term.entity.entity_type == "person" for term in terms)
            first_token = key.split()[0] if key.split() else ""
            if first_token and not _first_token_present(first_token, is_person_term, text_tokens, person_text_tokens):
                continue
            pattern = phrase_pattern(terms[0].text, person_name=is_person_term)
            if pattern is None:
                continue
            unique_entities = _unique_entities(term.entity for term in terms)
            for regex_match in pattern.finditer(text):
                start, end = regex_match.span()
                if _overlaps(start, end, occupied):
                    continue
                mention = regex_match.group(0)
                if _is_lowercase_single_person_mention(terms, mention):
                    continue
                if len(unique_entities) != 1:
                    ambiguous.append(
                        AmbiguousMatch(
                            text=mention,
                            start=start,
                            end=end,
                            candidates=tuple(unique_entities),
                            reason="ambiguous alias or name",
                        )
                    )
                    occupied.append((start, end))
                    continue
                term = terms[0]
                if _is_contextual_org_acronym(term):
                    confidence = _contextual_org_acronym_confidence(term, start, accepted)
                    match_type = "context_acronym"
                    if confidence < 0.86:
                        continue
                elif _is_weak_org_alias(term):
                    confidence = _weak_org_alias_confidence(term, mention, text, start, end, accepted)
                    match_type = "context_alias"
                    if confidence < 0.6:
                        continue
                    if confidence < 0.86:
                        ambiguous.append(
                            AmbiguousMatch(
                                text=mention,
                                start=start,
                                end=end,
                                candidates=(term.entity,),
                                reason="weak alias lacks context",
                            )
                        )
                        continue
                else:
                    confidence, match_type = _score(term, mention, start, end, ner_ranges)
                if confidence < 0.86:
                    ambiguous.append(
                        AmbiguousMatch(
                            text=mention,
                            start=start,
                            end=end,
                            candidates=(term.entity,),
                            reason="low confidence",
                        )
                    )
                    continue
                accepted.append(
                    EntityMatch(
                        entity=term.entity,
                        start=start,
                        end=end,
                        text=mention,
                        confidence=confidence,
                        match_type=match_type,
                    )
                )
                occupied.append((start, end))
        context_matches, context_ambiguous = _context_person_token_matches(text, accepted, occupied)
        accepted.extend(context_matches)
        ambiguous.extend(context_ambiguous)
        accepted.sort(key=lambda item: item.start)
        ambiguous.sort(key=lambda item: item.start)
        return MatchResult(matches=accepted, ambiguous_matches=ambiguous)

    def _iter_terms_longest_first(self) -> list[tuple[str, list[_Term]]]:
        return sorted(self._terms_by_key.items(), key=lambda item: len(item[0]), reverse=True)

    def _iter_candidate_terms_longest_first(
        self,
        text_tokens: set[str],
        person_text_tokens: set[str],
    ) -> list[tuple[str, list[_Term]]]:
        candidate_keys: set[str] = set()
        for token in text_tokens | person_text_tokens:
            candidate_keys.update(self._candidate_keys_by_token.get(token, ()))
        return sorted(
            ((key, self._terms_by_key[key]) for key in candidate_keys),
            key=lambda item: len(item[0]),
            reverse=True,
        )

    @staticmethod
    def _build_terms(entities: list[LegalEntity]) -> dict[str, list[_Term]]:
        terms_by_key: dict[str, list[_Term]] = {}
        for entity in entities:
            surfaces = [(entity.name, "exact")]
            surfaces.extend((alias, "alias") for alias in entity.aliases)
            surfaces.extend((alias, "runtime_form") for alias in entity.metadata.get("runtime_forms", ()) if isinstance(alias, str))
            surfaces.extend((alias, "person_alias") for alias in _person_name_variants(entity))
            surfaces.extend((alias, "acronym") for alias in _organization_acronyms(entity))
            surfaces.extend((alias, "component") for alias in _organization_components(entity))
            for surface, kind in surfaces:
                if not _significant_surface(surface, kind):
                    continue
                key = normalize_key(surface)
                if not key:
                    continue
                terms_by_key.setdefault(key, []).append(_Term(surface, kind, entity, key))
        return terms_by_key

    @staticmethod
    def _build_candidate_index(terms_by_key: dict[str, list[_Term]]) -> dict[str, set[str]]:
        candidate_keys_by_token: dict[str, set[str]] = {}
        token_cache: dict[tuple[str, bool], set[str]] = {}
        for key, terms in terms_by_key.items():
            first_token = key.split()[0] if key.split() else ""
            if not first_token:
                continue
            is_person_term = any(term.entity.entity_type == "person" for term in terms)
            index_tokens = set()
            first_tokens = {first_token}
            if is_person_term:
                first_tokens.update(_surface_first_tokens(terms))
            for token in first_tokens:
                cache_key = (token, is_person_term)
                if cache_key not in token_cache:
                    token_cache[cache_key] = person_search_keys(token) if is_person_term else {token}
                index_tokens.update(token_cache[cache_key])
            for token in index_tokens:
                candidate_keys_by_token.setdefault(token, set()).add(key)
        return candidate_keys_by_token

    @staticmethod
    def _build_ner() -> Any | None:
        try:
            from natasha import Doc, NewsEmbedding, NewsNERTagger, Segmenter
        except ModuleNotFoundError:
            LOGGER.info("Natasha is not installed; using registry-pattern matching only.")
            return None
        try:
            return {
                "Doc": Doc,
                "segmenter": Segmenter(),
                "tagger": NewsNERTagger(NewsEmbedding()),
            }
        except Exception as exc:
            LOGGER.warning("Natasha initialization failed: %s", exc)
            return None

    def _extract_ner_ranges(self, text: str) -> list[tuple[int, int]]:
        if self._ner is None:
            return []
        doc = self._ner["Doc"](text)
        doc.segment(self._ner["segmenter"])
        doc.tag_ner(self._ner["tagger"])
        return [
            (span.start, span.stop)
            for span in doc.spans
            if getattr(span, "type", "") in {"PER", "ORG"}
        ]


def _score(term: _Term, mention: str, start: int, end: int, ner_ranges: list[tuple[int, int]]) -> tuple[float, str]:
    mention_key = normalize_key(mention)
    mention_norm = normalize_text(mention)
    term_norm = normalize_text(term.text)
    if mention_norm == term_norm:
        return (0.99 if term.kind == "exact" else 0.95), term.kind
    if term.entity.entity_type == "person":
        person_score = _person_declension_score(term.text, mention)
        if person_score >= 0.95:
            return _boost_with_ner(0.93, start, end, ner_ranges), term.kind
    if mention_key == term.key:
        return _boost_with_ner(0.9, start, end, ner_ranges), "partial"
    term_tokens = set(term.key.split())
    mention_tokens = set(mention_key.split())
    if not term_tokens:
        return 0.0, "unknown"
    overlap = len(term_tokens & mention_tokens) / len(term_tokens)
    if overlap >= 0.8 and len(mention_tokens) >= 2:
        return _boost_with_ner(0.87, start, end, ner_ranges), "partial"
    return overlap, "partial"


def _significant_surface(surface: str, kind: str) -> bool:
    if kind != "runtime_form":
        return significant_alias(surface)
    normalized = normalize_text(surface)
    return bool(normalized) and len(normalized.replace(" ", "")) >= 3


def _person_declension_score(term_text: str, mention: str) -> float:
    term_tokens = tokenize(term_text)
    mention_tokens = tokenize(mention)
    if not term_tokens or len(term_tokens) != len(mention_tokens):
        return 0.0
    matched = 0
    for term_token, mention_token in zip(term_tokens, mention_tokens):
        if person_search_keys(term_token) & person_search_keys(mention_token):
            matched += 1
    return matched / len(term_tokens)


def _is_weak_org_alias(term: _Term) -> bool:
    if term.entity.entity_type != "organization" or term.kind != "alias":
        return False
    tokens = tokenize(term.text)
    if len(tokens) != 1:
        return False
    raw = re.sub(r"[^A-Za-zА-Яа-яЁё0-9]+", "", term.text.strip())
    if re.fullmatch(r"[A-ZА-ЯЁ0-9]{2,12}", raw):
        return False
    return bool(re.fullmatch(r"[а-яё]+", normalize_text(term.text)))


def _is_contextual_org_acronym(term: _Term) -> bool:
    if term.entity.entity_type != "organization" or term.kind not in {"alias", "acronym"}:
        return False
    if _is_forced_builtin_acronym(term):
        return False
    raw = re.sub(r"[^A-Za-zА-Яа-яЁё0-9]+", "", term.text.strip())
    return bool(re.fullmatch(r"[A-ZА-ЯЁ0-9]{2,12}", raw))


def _is_forced_builtin_acronym(term: _Term) -> bool:
    sources = {source.strip() for source in term.entity.source.split(";")}
    return "builtins" in sources and term.key == normalize_key("АУЕ")


def _contextual_org_acronym_confidence(
    term: _Term,
    start: int,
    accepted: list[EntityMatch],
) -> float:
    active = any(
        match.entity.id == term.entity.id
        and match.end <= start
        and match.match_type not in {"context_alias", "context_acronym"}
        and len(tokenize(match.text)) >= 2
        for match in accepted
    )
    return 0.95 if active else 0.0


def _weak_org_alias_confidence(
    term: _Term,
    mention: str,
    text: str,
    start: int,
    end: int,
    accepted: list[EntityMatch],
) -> float:
    score = 0.0
    active = any(
        match.entity.id == term.entity.id
        and match.end <= start
        and match.match_type != "context_alias"
        and len(tokenize(match.text)) >= 2
        for match in accepted
    )
    quoted = _is_quoted_mention(text, start, end)
    context_tokens = _context_tokens(text, start, end)
    has_org_context = bool(context_tokens & ORG_CONTEXT_WORDS)
    has_entity_context = bool(context_tokens & _entity_context_tokens(term))
    negative_context = _has_negative_weak_alias_context(text, start)

    if active:
        score += 0.88
    if quoted:
        score += 0.35
    if has_org_context:
        score += 0.35
    if has_entity_context:
        score += 0.25
    if mention and mention[0].isupper():
        score += 0.1
    if negative_context:
        score -= 0.45
    if mention and mention[0].islower() and not (active or quoted or has_org_context or has_entity_context):
        score -= 0.25
    return max(0.0, min(score, 0.99))


def _is_quoted_mention(text: str, start: int, end: int) -> bool:
    left = text[:start].rstrip()
    right = text[end:].lstrip()
    return bool(left and right and left[-1] in "\"'«“„" and right[0] in "\"'»”")


def _context_tokens(text: str, start: int, end: int, radius: int = 80) -> set[str]:
    window = text[max(0, start - radius) : min(len(text), end + radius)]
    return set(tokenize(window))


def _entity_context_tokens(term: _Term) -> set[str]:
    alias_tokens = set(tokenize(term.text))
    return {
        token
        for token in tokenize(term.entity.name)
        if len(token) >= 4 and token not in alias_tokens and token not in ORG_CONTEXT_WORDS
    }


def _has_negative_weak_alias_context(text: str, start: int) -> bool:
    left_tokens = tokenize(text[max(0, start - 50) : start])
    if not left_tokens:
        return False
    return left_tokens[-1] in WEAK_ALIAS_NEGATIVE_LEFT


def _unique_entities(entities) -> list[LegalEntity]:
    by_id: dict[str, LegalEntity] = {}
    for entity in entities:
        by_id[entity.id] = entity
    return list(by_id.values())


def _surface_first_tokens(terms: list[_Term]) -> set[str]:
    first_tokens: set[str] = set()
    for term in terms:
        tokens = tokenize(term.text)
        if tokens:
            first_tokens.add(tokens[0])
    return first_tokens


def _context_person_token_matches(
    text: str,
    accepted: list[EntityMatch],
    occupied: list[tuple[int, int]],
) -> tuple[list[EntityMatch], list[AmbiguousMatch]]:
    activations: dict[tuple[str, str], list[tuple[int, LegalEntity, str]]] = {}
    for match in accepted:
        if match.entity.entity_type != "person" or len(tokenize(match.text)) < 2:
            continue
        name_tokens = tokenize(match.entity.name)
        if len(name_tokens) < 2:
            continue
        for role, surface in (("surname", name_tokens[0]), ("first_name", name_tokens[1])):
            if len(surface) < 2:
                continue
            token_key = normalize_key(surface)
            if not token_key:
                continue
            activations.setdefault((role, token_key), []).append((match.end, match.entity, surface))

    context_matches: list[EntityMatch] = []
    ambiguous_matches: list[AmbiguousMatch] = []
    for (role, _token_key), token_activations in activations.items():
        pattern = phrase_pattern(token_activations[0][2], person_name=True)
        if pattern is None:
            continue
        for regex_match in pattern.finditer(text):
            start, end = regex_match.span()
            if _overlaps(start, end, occupied):
                continue
            active_entities = _unique_entities(
                entity for activation_end, entity, _ in token_activations if activation_end <= start
            )
            if not active_entities:
                continue
            mention = regex_match.group(0)
            if len(active_entities) != 1:
                ambiguous_matches.append(
                    AmbiguousMatch(
                        text=mention,
                        start=start,
                        end=end,
                        candidates=tuple(active_entities),
                        reason=f"ambiguous context {role}",
                    )
                )
                occupied.append((start, end))
                continue
            entity = active_entities[0]
            context_matches.append(
                EntityMatch(
                    entity=entity,
                    start=start,
                    end=end,
                    text=mention,
                    confidence=0.88,
                    match_type=f"context_{role}",
                )
            )
            occupied.append((start, end))
    return context_matches, ambiguous_matches


def _first_token_present(
    first_token: str,
    is_person_term: bool,
    text_tokens: set[str],
    person_text_tokens: set[str],
) -> bool:
    if not is_person_term:
        return first_token in text_tokens
    return True


def _is_lowercase_single_person_mention(terms: list[_Term], mention: str) -> bool:
    if not mention or mention[0].isupper():
        return False
    if not any(term.entity.entity_type == "person" for term in terms):
        return False
    return all(len(tokenize(term.text)) == 1 for term in terms)


def _person_search_tokens(text: str) -> set[str]:
    tokens: set[str] = set()
    for token in tokenize(text):
        tokens.update(person_search_keys(token))
    return tokens


def _person_name_variants(entity: LegalEntity) -> tuple[str, ...]:
    if entity.entity_type != "person":
        return ()
    tokens = tokenize(entity.name)
    if len(tokens) < 2:
        return ()
    last_name, first_name = tokens[0], tokens[1]
    variants = [
        f"{first_name} {last_name}",
        f"{last_name} {first_name}",
    ]
    if len(tokens) >= 3:
        patronymic = tokens[2]
        variants.extend(
            [
                f"{first_name} {patronymic} {last_name}",
                f"{first_name} {last_name} {patronymic}",
                f"{last_name} {first_name} {patronymic}",
                f"{last_name} {patronymic} {first_name}",
            ]
        )
    return tuple(dict.fromkeys(variants))


def _organization_acronyms(entity: LegalEntity) -> tuple[str, ...]:
    if entity.entity_type != "organization":
        return ()
    acronyms: list[str] = []
    for surface in (entity.name, *entity.aliases):
        acronym = _acronym(surface)
        if acronym:
            acronyms.append(acronym)
    return tuple(dict.fromkeys(acronyms))


def _organization_components(entity: LegalEntity) -> tuple[str, ...]:
    if entity.entity_type != "organization":
        return ()
    components: list[str] = []
    for surface in (entity.name, *entity.aliases):
        for raw_token in _raw_tokens(surface):
            if _indexable_component(raw_token):
                components.append(raw_token.strip(".,;:()[]{}\"'«»“”"))
    return tuple(dict.fromkeys(components))


def _raw_tokens(value: str) -> list[str]:
    return re.findall(r"[A-Za-zА-Яа-яЁё0-9]+(?:[-'][A-Za-zА-Яа-яЁё0-9]+)*", value)


def _indexable_component(token: str) -> bool:
    cleaned = token.strip(".,;:()[]{}\"'«»“”")
    if len(cleaned) < 4:
        return False
    if re.fullmatch(r"[A-Za-z][A-Za-z0-9-]*", cleaned):
        return True
    return False


def _acronym(value: str) -> str:
    stop_words = {"некоммерческая", "организация", "общественная", "объединение", "ано", "но"}
    tokens = [token for token in tokenize(value) if token not in stop_words]
    if len(tokens) < 2:
        return ""
    letters = "".join(token[0] for token in tokens if token and len(token) > 1)
    if 2 <= len(letters) <= 8:
        return letters.upper()
    return ""


def _overlaps(start: int, end: int, ranges: list[tuple[int, int]]) -> bool:
    return any(start < existing_end and end > existing_start for existing_start, existing_end in ranges)


def _boost_with_ner(confidence: float, start: int, end: int, ner_ranges: list[tuple[int, int]]) -> float:
    if any(start >= ner_start and end <= ner_end for ner_start, ner_end in ner_ranges):
        return min(confidence + 0.04, 0.99)
    return confidence
