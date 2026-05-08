from __future__ import annotations

import re
from dataclasses import dataclass, field


@dataclass(frozen=True)
class EntityTypeNormalizationPolicy:
    synonyms: dict[str, str] = field(default_factory=dict)
    null_sentinel: str = "__null__"


POWER_ATLAS_ENTITY_TYPE_NORMALIZATION_POLICY = EntityTypeNormalizationPolicy(
    synonyms={
        "ORG": "Organization",
        "Company": "Organization",
        "organization": "Organization",
        "PERSON": "Person",
        "person": "Person",
    }
)


_SAFE_CYPHER_VAR_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*(?:\.[A-Za-z_][A-Za-z0-9_]*)*$")


def get_default_entity_type_normalization_policy() -> EntityTypeNormalizationPolicy:
    return POWER_ATLAS_ENTITY_TYPE_NORMALIZATION_POLICY


def normalize_entity_type(
    entity_type: str | None,
    entity_type_policy: EntityTypeNormalizationPolicy | None = None,
) -> str | None:
    resolved_policy = (
        POWER_ATLAS_ENTITY_TYPE_NORMALIZATION_POLICY
        if entity_type_policy is None
        else entity_type_policy
    )
    stripped_entity_type = (entity_type or "").strip()
    if not stripped_entity_type:
        return None
    return resolved_policy.synonyms.get(stripped_entity_type, stripped_entity_type)


def _escape_cypher_string(value: str) -> str:
    return value.replace("'", "''")


def build_entity_type_cypher_case(
    var: str,
    unknown_label: str = "UNKNOWN",
    *,
    entity_type_policy: EntityTypeNormalizationPolicy | None = None,
) -> str:
    if not _SAFE_CYPHER_VAR_RE.fullmatch(var):
        raise ValueError(
            "var must be a dot-separated identifier expression like 'm.entity_type'"
        )

    resolved_policy = (
        POWER_ATLAS_ENTITY_TYPE_NORMALIZATION_POLICY
        if entity_type_policy is None
        else entity_type_policy
    )
    escaped_unknown_label = _escape_cypher_string(unknown_label)
    lines = [
        "CASE",
        f"  WHEN {var} IS NULL OR trim({var}) = '' THEN '{escaped_unknown_label}'",
    ]
    for raw, canonical in resolved_policy.synonyms.items():
        escaped_raw = _escape_cypher_string(raw)
        escaped_canonical = _escape_cypher_string(canonical)
        lines.append(f"  WHEN trim({var}) = '{escaped_raw}' THEN '{escaped_canonical}'")
    lines.append(f"  ELSE trim({var})")
    lines.append("END")
    return "\n".join(lines)


__all__ = [
    "EntityTypeNormalizationPolicy",
    "POWER_ATLAS_ENTITY_TYPE_NORMALIZATION_POLICY",
    "build_entity_type_cypher_case",
    "get_default_entity_type_normalization_policy",
    "normalize_entity_type",
]