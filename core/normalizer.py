from __future__ import annotations

from functools import lru_cache
import re
from collections.abc import Iterable

WORD_RE = re.compile(r"[A-Za-zА-Яа-яЁё0-9]+(?:[-'][A-Za-zА-Яа-яЁё0-9]+)*")
ALIAS_RE = re.compile(r"[\"«“](.+?)[\"»”]|\((.+?)\)")
RUSSIAN_TOKEN_RE = re.compile(r"^[а-яё]+$")
RUSSIAN_VOWELS = "аеёиоуыэюя"
COUNTRY_ALIASES = {
    "россия",
    "сша",
    "ссср",
    "рсфср",
    "тасср",
    "великобритания",
    "германия",
    "латвия",
    "литва",
    "эстония",
    "эстонская республика",
    "польша",
    "сочи",
    "украина",
    "франция",
    "чехия",
}
REPUBLIC_ALIASES = {
    "адыгея","алтай","башкортостан","бурятия","дагестан","донецкая народная республика","днр","ингушетия","кабардино балкария","калмыкия","карачаево черкесия","карелия","коми","крым","луганская народная республика","лнр","марий эл","мордовия","саха","саха якутия","северная осетия","северная осетия алания","татарстан","тыва","удмуртия","хакасия","чеченская республика","чечня","чувашия",
}
CITY_ALIASES = {
    "архангельск","астрахань","барнаул","белгород","брянск","владивосток","владикавказ","владимир","волгоград","вологда","воронеж","грозный","екатеринбург","ижевск","иркутск","казань","калининград","калуга","кемерово","киров","краснодар","красноярск","курган","курск","липецк","магадан","махачкала","москва","мурманск","нижний новгород","новгород","новосибирск","омск","оренбург","орел","пенза","пермь","петрозаводск","псков","ростов на дону","рязань","самара","санкт петербург","саранск","саратов","смоленск","сочи","ставрополь","сургут","тамбов","тверь","томск","тула","тюмень","улан удэ","ульяновск","уфа","хабаровск","чебоксары","челябинск","якутск","ярославль",
}
REGION_ALIASES = {
    "алтайский край","краснодарский край","красноярский край","пермский край","приморский край","ставропольский край","хабаровский край","амурская область","архангельская область","астраханская область","белгородская область","брянская область","владимирская область","волгоградская область","вологодская область","воронежская область","иркутская область","калининградская область","калужская область","кемеровская область","кировская область","курганская область","курская область","ленинградская область","липецкая область","магаданская область","московская область","мурманская область","нижегородская область","новгородская область","новосибирская область","омская область","оренбургская область","орловская область","пензенская область","ростовская область","рязанская область","самарская область","саратовская область","свердловская область","смоленская область","тамбовская область","тверская область","томская область","тульская область","тюменская область","ульяновская область","челябинская область","ярославская область",
}
GEOGRAPHIC_ONLY_ALIASES = COUNTRY_ALIASES | REPUBLIC_ALIASES | CITY_ALIASES | REGION_ALIASES | {
    "российская федерация","республика татарстан","республика башкортостан","республика дагестан","республика крым","республика бурятия","республика коми","республика карелия","республика марий эл","республика мордовия","республика саха","республика тыва","республика хакасия","удмуртская республика","чувашская республика",
}
GEOGRAPHIC_ADMIN_WORDS = {"автономная","автономный","город","государство","край","область","округ","район","республика","федерация"}
GENERIC_SHORT_ALIASES = {"база","мир","фонд","центр","проект","движение","компания","организация","суд","вместе","inc","llc","ltd","инк"} | COUNTRY_ALIASES
NOISY_ALIAS_PHRASES = (" на факультет "," факультет "," решение "," суд","суд ")

@lru_cache(maxsize=262144)
def normalize_text(value: str) -> str:
    text = value.replace("Ё", "Е").replace("ё", "е").lower()
    text = text.replace("\u00a0", " ")
    text = re.sub(r"[«»“”\"'`´]", "", text)
    text = re.sub(r"[\u2012-\u2015–—]+", " ", text)
    text = re.sub(r"[^0-9a-zа-я]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()

@lru_cache(maxsize=262144)
def normalize_key(value: str) -> str:
    return " ".join(stem_token(token) for token in tokenize(value))

@lru_cache(maxsize=262144)
def tokenize(value: str) -> tuple[str, ...]:
    return tuple(match.group(0) for match in WORD_RE.finditer(normalize_text(value)))

@lru_cache(maxsize=262144)
def stem_token(token: str) -> str:
    token = normalize_text(token)
    if not token:
        return token
    if re.fullmatch(r"[a-z0-9]+", token):
        return token
    endings = ("иями","ями","ами","ого","ему","ому","ими","ыми","ую","юю","ой","ей","ою","ею","ым","им","ых","их","ая","яя","ое","ее","ые","ие","ый","ий","ого","его","ом","ем","ах","ях","ам","ям","ов","ев","а","я","ы","и","е","у","ю","о")
    for ending in endings:
        if len(token) - len(ending) >= 4 and token.endswith(ending):
            return token[: -len(ending)]
    return token

def extract_aliases(value: str) -> tuple[str, ...]:
    aliases: list[str] = []
    for match in ALIAS_RE.finditer(value):
        raw = match.group(1) or match.group(2) or ""
        aliases.extend(split_aliases(raw))
        aliases.extend(_quoted_segments(raw))
    return unique_clean(aliases)

def _quoted_segments(value: str) -> list[str]:
    return [match.group(1) for match in re.finditer(r"[\"«“](.+?)[\"»”]", value) if match.group(1).strip()]

def split_aliases(value: str) -> list[str]:
    parts = re.split(r"\s*;\s*|\s*,\s*", value)
    return [part.strip() for part in parts if part.strip()]

def strip_alias_fragments(value: str) -> str:
    cleaned = ALIAS_RE.sub("", value)
    cleaned = re.sub(r"\s+", " ", cleaned)
    return cleaned.strip(" ,;")

def unique_clean(values: Iterable[str]) -> tuple[str, ...]:
    seen: dict[str, str] = {}
    for value in values:
        cleaned = re.sub(r"\s+", " ", str(value)).strip(" ,;")
        if not cleaned:
            continue
        key = normalize_text(cleaned)
        if key and key not in seen:
            seen[key] = cleaned
    return tuple(seen.values())

def significant_alias(value: str) -> bool:
    normalized = normalize_text(value)
    if geographic_only_alias(value):
        return False
    if normalized in GENERIC_SHORT_ALIASES:
        return False
    if any(phrase in f" {normalized} " for phrase in NOISY_ALIAS_PHRASES):
        return False
    if normalized.startswith(("инн ", "огрн ", "снилс ", "id ")):
        return False
    if re.fullmatch(r"\d+", normalized):
        return False
    raw = re.sub(r"[^A-Za-zА-Яа-яЁё0-9]+", "", value.strip())
    if re.fullmatch(r"[A-ZА-ЯЁ0-9]{3,}", raw):
        return True
    tokens = tokenize(value)
    if not tokens:
        return False
    if len(tokens) == 1 and normalized not in GENERIC_SHORT_ALIASES:
        raw = re.sub(r"[^A-Za-zА-Яа-яЁё0-9]+", "", value.strip())
        if re.fullmatch(r"[А-ЯЁ]{3,}", raw) and normalized in GENERIC_SHORT_ALIASES:
            return False
        if normalized in GENERIC_SHORT_ALIASES:
            return False
    if len(tokens) >= 2:
        if all(re.fullmatch(r"[a-z]+", token) and len(token) < 6 for token in tokens):
            return False
        return sum(len(token) >= 2 for token in tokens) >= 2
    token = tokens[0]
    if re.fullmatch(r"[a-z]+", token) and len(token) < 4:
        return False
    if re.fullmatch(r"[а-я]+", token) and len(token) < 5:
        return False
    return normalized not in GENERIC_SHORT_ALIASES

def geographic_only_alias(value: str) -> bool:
    normalized = normalize_text(value)
    if not normalized:
        return False
    if normalized in GEOGRAPHIC_ONLY_ALIASES:
        return True
    tokens = tokenize(value)
    if not tokens:
        return False
    if tokens[0] == "город" and " ".join(tokens[1:]) in CITY_ALIASES:
        return True
    if tokens[0] == "республика" and " ".join(tokens[1:]) in REPUBLIC_ALIASES:
        return True
    if tokens[-1] in {"область", "край", "округ", "район"}:
        return normalized in REGION_ALIASES
    meaningful_tokens = [token for token in tokens if token not in GEOGRAPHIC_ADMIN_WORDS]
    if not meaningful_tokens:
        return True
    meaningful = " ".join(meaningful_tokens)
    return meaningful in GEOGRAPHIC_ONLY_ALIASES

def has_word_boundaries(text: str, start: int, end: int) -> bool:
    before = text[start - 1] if start > 0 else ""
    after = text[end] if end < len(text) else ""
    return not _is_word_char(before) and not _is_word_char(after)

def _is_word_char(char: str) -> bool:
    return bool(char and re.match(r"[A-Za-zА-Яа-яЁё0-9_]", char))

@lru_cache(maxsize=131072)
def phrase_pattern(value: str, person_name: bool = False) -> re.Pattern[str] | None:
    tokens = tokenize(value)
    if not tokens:
        return None
    parts = [_token_pattern(token, person_name=person_name) for token in tokens]
    pattern = r"(?<![A-Za-zА-Яа-яЁё0-9_])" + r"[\W_]+".join(parts) + r"(?![A-Za-zА-Яа-яЁё0-9_])"
    return re.compile(pattern, re.IGNORECASE | re.UNICODE)

@lru_cache(maxsize=131072)
def person_search_keys(token: str) -> frozenset[str]:
    normalized = normalize_text(token)
    if not normalized:
        return frozenset()
    keys = {normalized, stem_token(normalized)}
    keys.update(_person_declension_stems(normalized))
    return frozenset(key for key in keys if key)

def _token_pattern(token: str, person_name: bool = False) -> str:
    normalized = normalize_text(token)
    if person_name and RUSSIAN_TOKEN_RE.fullmatch(normalized) and len(normalized) >= 3:
        return _person_token_pattern(normalized)
    if re.fullmatch(r"[а-я]+", normalized) and len(normalized) >= 4:
        stem = _yo_insensitive_literal(stem_token(normalized))
        return stem + r"[а-яё]*"
    return re.escape(token)

def _person_token_pattern(token: str) -> str:
    patterns = [_yo_insensitive_literal(token)]
    for stem, suffixes in _person_declension_patterns(token):
        if len(stem) >= 2:
            patterns.append(_yo_insensitive_literal(stem) + _yo_insensitive_regex(suffixes))
    fallback_stem = stem_token(token)
    if len(fallback_stem) >= 3 and fallback_stem != token:
        patterns.append(_yo_insensitive_literal(fallback_stem) + r"[а-яё]*")
    return "(?:" + "|".join(dict.fromkeys(patterns)) + ")"

def _yo_insensitive_literal(value: str) -> str:
    escaped = re.escape(value)
    return escaped.replace("е", "[её]").replace("Е", "[ЕЁ]")

def _yo_insensitive_regex(value: str) -> str:
    return value.replace("е", "[её]").replace("Е", "[ЕЁ]")

@lru_cache(maxsize=131072)
def _person_declension_patterns(token: str) -> tuple[tuple[str, str], ...]:
    adjective_suffixes = (r"(?:ый|ий|ой|ого|его|ому|ему|ым|им|ом|ем|ых|их|ыми|ими|ая|яя|ую|юю|ой|ей|ою|ею|ые|ие)")
    patterns: list[tuple[str, str]] = []
    if token.endswith(("ай", "ей")) and len(token) >= 4:
        patterns.append((token[:-1], r"(?:й|я|ю|ем|е)"))
    if token.endswith("ий") and len(token) >= 4:
        patterns.append((token[:-2], r"(?:ий|ия|ию|ием|ии|его|ему|им|ем|их|ими|ая|ую|ие)"))
    if token.endswith(("ый", "ой")) and len(token) >= 4:
        patterns.append((token[:-2], adjective_suffixes))
    if token.endswith("ь") and len(token) >= 4:
        patterns.append((token[:-1], r"(?:ь|я|ю|ем|е|и|ью)"))
    if token.endswith("ец") and len(token) >= 4:
        patterns.append((token[:-2], r"(?:ец|ца|цу|цом|це)"))
    if token.endswith("а") and len(token) >= 4:
        patterns.append((token[:-1], r"(?:а|ы|и|е|у|ой|ою|ей|ею)"))
    if token.endswith("я") and len(token) >= 4:
        patterns.append((token[:-1], r"(?:я|и|е|ю|ей|ею)"))
    if token[-1] not in RUSSIAN_VOWELS + "йь" and len(token) >= 3:
        patterns.append((token, r"(?:а|у|ом|ым|е|ы)?"))
    return tuple(patterns)

@lru_cache(maxsize=131072)
def _person_declension_stems(token: str) -> frozenset[str]:
    stems = {stem for stem, _ in _person_declension_patterns(token)}
    declined_endings = ("ого","его","ому","ему","ыми","ими","ием","цом","ем","ом","ых","их","ым","им","ия","ию","ии","ью","ой","ей","ою","ею","ца","цу","це","я","ю","а","у","е","и","ы")
    for ending in declined_endings:
        if len(token) - len(ending) >= 2 and token.endswith(ending):
            stems.add(token[: -len(ending)])
    return frozenset(stems)
