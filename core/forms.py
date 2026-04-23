from __future__ import annotations

from dataclasses import dataclass
import re

from .models import LegalEntity
from .normalizer import normalize_text, unique_clean


@dataclass(frozen=True)
class RuntimeForm:
    entity_id: str
    text: str
    source_type: str


def build_card_forms(
    entity: LegalEntity,
    manual_aliases: tuple[str, ...] = (),
    manual_forms: tuple[str, ...] = (),
    disabled_auto_forms: tuple[str, ...] = (),
) -> tuple[RuntimeForm, ...]:
    disabled = {normalize_text(value) for value in disabled_auto_forms if normalize_text(value)}
    seen: set[str] = set()
    forms: list[RuntimeForm] = []

    for value in _base_surfaces(entity):
        _append_form(forms, seen, entity.id, value, "base", disabled)
    for value in manual_aliases:
        _append_form(forms, seen, entity.id, value, "manual_alias", disabled)
    for value in manual_forms:
        _append_form(forms, seen, entity.id, value, "manual", disabled)
    for value in _transliterated_surfaces(*(item.text for item in forms)):
        _append_form(forms, seen, entity.id, value, "auto_translit", disabled)
    return tuple(forms)


def _append_form(
    forms: list[RuntimeForm],
    seen: set[str],
    entity_id: str,
    value: str,
    source_type: str,
    disabled: set[str],
) -> None:
    cleaned = re.sub(r"\s+", " ", str(value)).strip()
    key = normalize_text(cleaned)
    if not cleaned or not key or key in seen or key in disabled:
        return
    seen.add(key)
    forms.append(RuntimeForm(entity_id=entity_id, text=cleaned, source_type=source_type))


def _base_surfaces(entity: LegalEntity) -> tuple[str, ...]:
    values = [entity.name, *entity.aliases]
    if entity.entity_type == "person":
        tokens = _word_tokens(entity.name)
        if tokens and len(tokens[0]) >= 5:
            values.append(tokens[0])
    return unique_clean(values)


def _transliterated_surfaces(*values: str) -> tuple[str, ...]:
    variants: list[str] = []
    for value in values:
        if re.search(r"[А-Яа-яЁё]", value):
            variants.extend(_cyrillic_to_latin_variants(value))
        if re.search(r"[A-Za-z]", value):
            cyr_variant = _latin_to_cyrillic(value)
            if cyr_variant:
                variants.append(cyr_variant)
    return unique_clean(variants)


def _word_tokens(value: str) -> list[str]:
    return re.findall(r"[A-Za-zА-Яа-яЁё]+(?:[-'][A-Za-zА-Яа-яЁё]+)*", value)


def _cyrillic_to_latin_variants(value: str) -> tuple[str, ...]:
    table = {
        "а": "a",
        "б": "b",
        "в": "v",
        "г": "g",
        "д": "d",
        "е": "e",
        "ё": "e",
        "ж": "zh",
        "з": "z",
        "и": "i",
        "й": "y",
        "к": "k",
        "л": "l",
        "м": "m",
        "н": "n",
        "о": "o",
        "п": "p",
        "р": "r",
        "с": "s",
        "т": "t",
        "у": "u",
        "ф": "f",
        "х": "kh",
        "ц": "ts",
        "ч": "ch",
        "ш": "sh",
        "щ": "shch",
        "ъ": "",
        "ы": "y",
        "ь": "",
        "э": "e",
        "ю": "yu",
        "я": "ya",
        "-": "-",
        " ": " ",
    }
    transliterated = "".join(table.get(char.lower(), char) for char in value)
    variants = [transliterated[:1].upper() + transliterated[1:] if transliterated else ""]
    lowered = transliterated.lower()
    if "sht" in lowered:
        compact = lowered.replace("sht", "st")
        variants.append(compact[:1].upper() + compact[1:])
    return unique_clean(variants)


def _latin_to_cyrillic(value: str) -> str:
    lowered = normalize_text(value)
    if not lowered or not re.fullmatch(r"[a-z0-9 ]+", lowered):
        return ""
    lowered = lowered.replace("xxx", "кс")
    replacements = (
        ("shch", "щ"),
        ("sch", "щ"),
        ("yo", "е"),
        ("yu", "ю"),
        ("ya", "я"),
        ("zh", "ж"),
        ("kh", "х"),
        ("ts", "ц"),
        ("ch", "ч"),
        ("sh", "ш"),
    )
    for source, target in replacements:
        lowered = lowered.replace(source, target)
    table = {
        "a": "а",
        "b": "б",
        "c": "к",
        "d": "д",
        "e": "е",
        "f": "ф",
        "g": "г",
        "h": "х",
        "i": "и",
        "j": "й",
        "k": "к",
        "l": "л",
        "m": "м",
        "n": "н",
        "o": "о",
        "p": "п",
        "q": "к",
        "r": "р",
        "s": "с",
        "t": "т",
        "u": "у",
        "v": "в",
        "w": "в",
        "x": "кс",
        "y": "и",
        "z": "з",
        " ": " ",
        "0": "0",
        "1": "1",
        "2": "2",
        "3": "3",
        "4": "4",
        "5": "5",
        "6": "6",
        "7": "7",
        "8": "8",
        "9": "9",
    }
    converted = "".join(table.get(char, char) for char in lowered)
    return converted[:1].upper() + converted[1:] if converted else ""
