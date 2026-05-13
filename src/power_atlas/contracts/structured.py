from __future__ import annotations

import re
from dataclasses import dataclass, field


@dataclass(frozen=True)
class StructuredSchemaContract:
    entity_file_name: str = "entities.csv"
    fact_file_name: str = "facts.csv"
    relationship_file_name: str = "relationships.csv"
    claim_file_name: str = "claims.csv"
    file_headers: dict[str, tuple[str, ...]] = field(default_factory=lambda: {
        "entities.csv": (
            "entity_id",
            "name",
            "entity_type",
            "aliases",
            "description",
            "wikidata_url",
        ),
        "facts.csv": (
            "fact_id",
            "subject_id",
            "subject_label",
            "predicate_pid",
            "predicate_label",
            "value",
            "value_type",
            "source",
            "source_url",
            "retrieved_at",
        ),
        "relationships.csv": (
            "rel_id",
            "subject_id",
            "subject_label",
            "predicate_pid",
            "predicate_label",
            "object_id",
            "object_label",
            "object_entity_type",
            "source",
            "source_url",
            "retrieved_at",
        ),
        "claims.csv": (
            "claim_id",
            "claim_type",
            "subject_id",
            "subject_label",
            "predicate_pid",
            "predicate_label",
            "object_id",
            "object_label",
            "value",
            "value_type",
            "claim_text",
            "confidence",
            "source",
            "source_url",
            "retrieved_at",
            "source_row_id",
        ),
    })
    id_patterns: dict[str, re.Pattern[str]] = field(default_factory=lambda: {
        "entity_id": re.compile(r"^Q\d+$"),
        "fact_id": re.compile(r"^F\d+$"),
        "rel_id": re.compile(r"^R\d+$"),
        "claim_id": re.compile(r"^C\d+$"),
        "predicate_pid": re.compile(r"^P\d+$"),
    })
    value_types: frozenset[str] = field(
        default_factory=lambda: frozenset(
            {"date", "url", "entity", "string", "number", "boolean"}
        )
    )
    csv_first_data_row: int = 2
    common_predicate_labels: dict[str, str] = field(default_factory=lambda: {
        "P22": "father",
        "P25": "mother",
        "P26": "spouse",
        "P39": "position held",
        "P108": "employer",
        "P112": "founded by",
        "P169": "chief executive officer",
        "P463": "member of",
        "P569": "date of birth",
        "P570": "date of death",
        "P571": "inception",
        "P856": "official website",
        "P1830": "owner of",
    })

    @property
    def file_names(self) -> tuple[str, str, str, str]:
        return (
            self.entity_file_name,
            self.fact_file_name,
            self.relationship_file_name,
            self.claim_file_name,
        )

    @property
    def id_field_by_file_name(self) -> dict[str, str]:
        return {
            self.entity_file_name: "entity_id",
            self.fact_file_name: "fact_id",
            self.relationship_file_name: "rel_id",
            self.claim_file_name: "claim_id",
        }


@dataclass(frozen=True)
class StructuredGraphShapeContract:
    source_label: str = "Source"
    entity_label: str = "CanonicalEntity"
    fact_label: str = "Fact"
    relationship_label: str = "Relationship"
    claim_label: str = "Claim"
    asserted_in_relationship: str = "ASSERTED_IN"
    cited_from_relationship: str = "CITED_FROM"
    about_relationship: str = "ABOUT"
    targets_relationship: str = "TARGETS"
    supported_by_relationship: str = "SUPPORTED_BY"
    subject_relationship: str = "SUBJECT"
    object_relationship: str = "OBJECT"


POWER_ATLAS_STRUCTURED_GRAPH_SHAPE_CONTRACT = StructuredGraphShapeContract()


POWER_ATLAS_STRUCTURED_SCHEMA_CONTRACT = StructuredSchemaContract()


def get_default_structured_schema_contract() -> StructuredSchemaContract:
    return POWER_ATLAS_STRUCTURED_SCHEMA_CONTRACT


def get_default_structured_graph_shape_contract() -> StructuredGraphShapeContract:
    return POWER_ATLAS_STRUCTURED_GRAPH_SHAPE_CONTRACT


STRUCTURED_FILE_HEADERS: dict[str, list[str]] = {
    file_name: list(headers)
    for file_name, headers in POWER_ATLAS_STRUCTURED_SCHEMA_CONTRACT.file_headers.items()
}
ID_PATTERNS = dict(POWER_ATLAS_STRUCTURED_SCHEMA_CONTRACT.id_patterns)
VALUE_TYPES = set(POWER_ATLAS_STRUCTURED_SCHEMA_CONTRACT.value_types)
CSV_FIRST_DATA_ROW = POWER_ATLAS_STRUCTURED_SCHEMA_CONTRACT.csv_first_data_row
COMMON_PREDICATE_LABELS = dict(
    POWER_ATLAS_STRUCTURED_SCHEMA_CONTRACT.common_predicate_labels
)

__all__ = [
    "COMMON_PREDICATE_LABELS",
    "CSV_FIRST_DATA_ROW",
    "ID_PATTERNS",
    "POWER_ATLAS_STRUCTURED_GRAPH_SHAPE_CONTRACT",
    "POWER_ATLAS_STRUCTURED_SCHEMA_CONTRACT",
    "StructuredGraphShapeContract",
    "STRUCTURED_FILE_HEADERS",
    "StructuredSchemaContract",
    "VALUE_TYPES",
    "get_default_structured_graph_shape_contract",
    "get_default_structured_schema_contract",
]