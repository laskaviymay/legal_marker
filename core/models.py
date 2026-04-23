from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


STATUS_LABELS: dict[str, str] = {
    "foreign_agent": "признан иноагентом",
    "terrorist_extremist": "внесен в перечень террористов и экстремистов",
    "extremist": "включен в перечень экстремистов",
    "terrorist": "включен в перечень террористов",
    "undesirable_organization": "признана нежелательной организацией",
    "extremist_material": "включен в федеральный список экстремистских материалов",
}


STATUS_ORDER: tuple[str, ...] = (
    "foreign_agent",
    "terrorist_extremist",
    "terrorist",
    "extremist",
    "undesirable_organization",
    "extremist_material",
)


@dataclass(frozen=True)
class LegalEntity:
    id: str
    name: str
    entity_type: str
    statuses: tuple[str, ...]
    aliases: tuple[str, ...] = ()
    source: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def combined_status(self) -> str:
        labels = self._combined_status_labels()
        if not labels:
            return "имеет юридически значимый статус"
        if len(labels) == 1:
            return labels[0]
        return ", ".join(labels[:-1]) + " и " + labels[-1]

    def _combined_status_labels(self) -> list[str]:
        statuses = set(self.statuses)
        labels: list[str] = []
        terrorist_undesirable = {"terrorist_extremist", "undesirable_organization"}
        if self.entity_type == "organization" and terrorist_undesirable <= statuses:
            labels.append("Признана в РФ террористической и нежелательной организацией")
            statuses -= terrorist_undesirable
        if "terrorist_extremist" in statuses:
            statuses.discard("extremist")
        labels.extend(STATUS_LABELS[status] for status in STATUS_ORDER if status in statuses)
        return labels

    def merged_with(self, other: "LegalEntity") -> "LegalEntity":
        statuses = tuple(status for status in STATUS_ORDER if status in set(self.statuses + other.statuses))
        aliases = tuple(dict.fromkeys(self.aliases + other.aliases + (other.name,)))
        metadata = {**self.metadata, **other.metadata}
        return LegalEntity(
            id=self.id,
            name=self.name,
            entity_type=self.entity_type if self.entity_type != "unknown" else other.entity_type,
            statuses=statuses,
            aliases=aliases,
            source="; ".join(filter(None, dict.fromkeys([self.source, other.source]))),
            metadata=metadata,
        )

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["statuses"] = list(self.statuses)
        data["aliases"] = list(self.aliases)
        return data

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "LegalEntity":
        return cls(
            id=str(data["id"]),
            name=str(data["name"]),
            entity_type=str(data.get("entity_type", "unknown")),
            statuses=tuple(data.get("statuses", ())),
            aliases=tuple(data.get("aliases", ())),
            source=str(data.get("source", "")),
            metadata=dict(data.get("metadata", {})),
        )


@dataclass(frozen=True)
class EntityMatch:
    entity: LegalEntity
    start: int
    end: int
    text: str
    confidence: float
    match_type: str


@dataclass(frozen=True)
class AmbiguousMatch:
    text: str
    start: int
    end: int
    candidates: tuple[LegalEntity, ...]
    reason: str


@dataclass(frozen=True)
class MatchResult:
    matches: list[EntityMatch]
    ambiguous_matches: list[AmbiguousMatch]


@dataclass(frozen=True)
class AnnotationResult:
    marked_text: str
    matches: list[EntityMatch]
    ambiguous_matches: list[AmbiguousMatch]
    marker_by_status: dict[str, str]
