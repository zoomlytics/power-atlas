"""Versioned constants and graph contracts for entity resolution pipeline outputs."""

from __future__ import annotations

from dataclasses import dataclass


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


def get_default_entity_resolution_graph_contract() -> EntityResolutionGraphContract:
	return POWER_ATLAS_ENTITY_RESOLUTION_GRAPH_CONTRACT


__all__ = [
	"ALIGNMENT_VERSION",
	"EntityResolutionGraphContract",
	"POWER_ATLAS_ENTITY_RESOLUTION_GRAPH_CONTRACT",
	"get_default_entity_resolution_graph_contract",
]
