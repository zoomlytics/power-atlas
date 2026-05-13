"""Versioned constants and graph contracts for entity resolution pipeline outputs."""

from __future__ import annotations

import re
from dataclasses import dataclass
from dataclasses import field
from typing import Any, Callable


ALIGNMENT_VERSION: str = "v1.0"


@dataclass(frozen=True)
class EntityResolutionGraphContract:
	mention_label: str = "EntityMention"
	canonical_label: str = "CanonicalEntity"
	cluster_label: str = "ResolvedEntityCluster"
	resolves_to_relationship: str = "RESOLVES_TO"
	member_of_relationship: str = "MEMBER_OF"
	candidate_match_relationship: str = "CANDIDATE_MATCH"
	aligned_with_relationship: str = "ALIGNED_WITH"


POWER_ATLAS_ENTITY_RESOLUTION_GRAPH_CONTRACT = EntityResolutionGraphContract()


@dataclass(frozen=True)
class EntityResolutionCanonicalLookupContract:
	canonical_entity_id_field: str = "entity_id"
	canonical_run_id_field: str = "run_id"
	canonical_name_field: str = "name"
	canonical_aliases_field: str = "aliases"
	qid_pattern: re.Pattern[str] = field(default_factory=lambda: re.compile(r"^Q\d+$"))
	alias_delimiters: tuple[str, ...] = ("|", ",")
	qid_exact_method: str = "qid_exact"
	label_exact_method: str = "label_exact"
	alias_exact_method: str = "alias_exact"
	unresolved_method: str = "label_cluster"
	qid_exact_confidence: float = 1.0
	label_exact_confidence: float = 0.9
	alias_exact_confidence: float = 0.8
	aligned_status: str = "aligned"


POWER_ATLAS_ENTITY_RESOLUTION_CANONICAL_LOOKUP_CONTRACT = (
	EntityResolutionCanonicalLookupContract()
)


AlignmentKeyBuilder = Callable[[dict[str, Any]], tuple[str, ...]]


def _default_alignment_keys(cluster: dict[str, Any]) -> tuple[str, ...]:
	key = cluster.get("normalized_text")
	if isinstance(key, str) and key:
		return (key,)
	return ()


@dataclass(frozen=True)
class EntityResolutionAlignmentStep:
	lookup_table: str
	cluster_keys: AlignmentKeyBuilder = _default_alignment_keys
	method: str | None = None
	score: float | None = None
	status: str | None = None


@dataclass(frozen=True)
class EntityResolutionAlignmentContract:
	steps: tuple[EntityResolutionAlignmentStep, ...] = field(
		default_factory=lambda: (
			EntityResolutionAlignmentStep(lookup_table="label"),
			EntityResolutionAlignmentStep(lookup_table="alias"),
		)
	)


POWER_ATLAS_ENTITY_RESOLUTION_ALIGNMENT_CONTRACT = EntityResolutionAlignmentContract()


DatasetIdSelector = Callable[[Any, str | None, str | None], str | None]


def _default_select_dataset_id(
	config: Any,
	dataset_id: str | None,
	dataset_name: str | None,
) -> str | None:
	if isinstance(dataset_id, str) and dataset_id:
		return dataset_id

	configured_dataset_name = dataset_name or getattr(config, "dataset_name", None)
	if isinstance(configured_dataset_name, str) and configured_dataset_name:
		from power_atlas.contracts.paths import resolve_dataset_root

		return resolve_dataset_root(configured_dataset_name).dataset_id
	return None


@dataclass(frozen=True)
class EntityResolutionDatasetSelectionContract:
	select_dataset_id: DatasetIdSelector = _default_select_dataset_id


POWER_ATLAS_ENTITY_RESOLUTION_DATASET_SELECTION_CONTRACT = (
	EntityResolutionDatasetSelectionContract()
)


def get_default_entity_resolution_graph_contract() -> EntityResolutionGraphContract:
	return POWER_ATLAS_ENTITY_RESOLUTION_GRAPH_CONTRACT


def get_default_entity_resolution_canonical_lookup_contract() -> EntityResolutionCanonicalLookupContract:
	return POWER_ATLAS_ENTITY_RESOLUTION_CANONICAL_LOOKUP_CONTRACT


def get_default_entity_resolution_alignment_contract() -> EntityResolutionAlignmentContract:
	return POWER_ATLAS_ENTITY_RESOLUTION_ALIGNMENT_CONTRACT


def get_default_entity_resolution_dataset_selection_contract() -> EntityResolutionDatasetSelectionContract:
	return POWER_ATLAS_ENTITY_RESOLUTION_DATASET_SELECTION_CONTRACT


__all__ = [
	"ALIGNMENT_VERSION",
	"AlignmentKeyBuilder",
	"DatasetIdSelector",
	"EntityResolutionAlignmentContract",
	"EntityResolutionAlignmentStep",
	"EntityResolutionCanonicalLookupContract",
	"EntityResolutionDatasetSelectionContract",
	"EntityResolutionGraphContract",
	"POWER_ATLAS_ENTITY_RESOLUTION_ALIGNMENT_CONTRACT",
	"POWER_ATLAS_ENTITY_RESOLUTION_CANONICAL_LOOKUP_CONTRACT",
	"POWER_ATLAS_ENTITY_RESOLUTION_DATASET_SELECTION_CONTRACT",
	"POWER_ATLAS_ENTITY_RESOLUTION_GRAPH_CONTRACT",
	"get_default_entity_resolution_alignment_contract",
	"get_default_entity_resolution_canonical_lookup_contract",
	"get_default_entity_resolution_dataset_selection_contract",
	"get_default_entity_resolution_graph_contract",
]
