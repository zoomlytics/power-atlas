from __future__ import annotations

import re

STRUCTURED_FILE_HEADERS: dict[str, list[str]] = {
    "entities.csv": ["entity_id", "name", "entity_type", "aliases", "description", "wikidata_url"],
    "facts.csv": [
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
    ],
    "relationships.csv": [
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
    ],
    "claims.csv": [
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
    ],
}

ID_PATTERNS = {
    "entity_id": re.compile(r"^Q\d+$"),
    "fact_id": re.compile(r"^F\d+$"),
    "rel_id": re.compile(r"^R\d+$"),
    "claim_id": re.compile(r"^C\d+$"),
    "predicate_pid": re.compile(r"^P\d+$"),
}

VALUE_TYPES = {"date", "url", "entity", "string", "number", "boolean"}
CSV_FIRST_DATA_ROW = 2

COMMON_PREDICATE_LABELS = {
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
}

__all__ = [
    "COMMON_PREDICATE_LABELS",
    "CSV_FIRST_DATA_ROW",
    "ID_PATTERNS",
    "STRUCTURED_FILE_HEADERS",
    "VALUE_TYPES",
]