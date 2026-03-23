from __future__ import annotations

from neo4j_graphrag.experimental.components.schema import GraphSchema, NodeType, PropertyType, RelationshipType
from neo4j_graphrag.experimental.components.types import LexicalGraphConfig

from demo.contracts.pipeline import CHUNK_EMBEDDING_LABEL, CHUNK_EMBEDDING_PROPERTY


def claim_extraction_lexical_config() -> LexicalGraphConfig:
    return LexicalGraphConfig(
        chunk_node_label=CHUNK_EMBEDDING_LABEL,
        chunk_id_property="chunk_id",
        chunk_index_property="chunk_index",
        chunk_text_property="text",
        chunk_embedding_property=CHUNK_EMBEDDING_PROPERTY,
        node_to_chunk_relationship_type="MENTIONED_IN",
    )


def claim_extraction_schema() -> GraphSchema:
    return GraphSchema(
        node_types=[
            NodeType(
                label="ExtractedClaim",
                description="Claim extracted from unstructured chunk",
                properties=[
                    PropertyType(name="claim_text", type="STRING", required=True),
                    PropertyType(name="subject", type="STRING"),
                    PropertyType(name="predicate", type="STRING"),
                    PropertyType(name="object", type="STRING"),
                    PropertyType(name="confidence", type="FLOAT"),
                ],
                additional_properties=True,
            ),
            NodeType(
                label="EntityMention",
                description="Entity mention extracted from text chunk",
                properties=[
                    PropertyType(name="name", type="STRING", required=True),
                    PropertyType(name="entity_type", type="STRING"),
                    PropertyType(name="confidence", type="FLOAT"),
                ],
                additional_properties=True,
            ),
        ],
        relationship_types=[
            RelationshipType(label="MENTIONS"),
            RelationshipType(label="SUPPORTED_BY"),
            RelationshipType(label="MENTIONED_IN"),
            # Participation edges: claim → mention for any argument role (v0.3 model).
            # Created by the extraction stage (inline, after claims and mentions are
            # written) and also available via the standalone claim-participation stage.
            # Properties: role (subject | object | …), run_id, source_uri, match_method
            #   (raw_exact | casefold_exact | normalized_exact).
            # See docs/architecture/claim-argument-model-v0.3.md for the decision record.
            RelationshipType(label="HAS_PARTICIPANT"),
        ],
    )


def resolution_layer_schema() -> GraphSchema:
    """Schema for resolution-layer artifacts created programmatically by the entity resolution stage.

    This schema is not intended to be used as an extraction target for the LLM.
    """
    return GraphSchema(
        node_types=[
            NodeType(
                label="ResolvedEntityCluster",
                description=(
                    "Provisional cluster of EntityMention nodes believed to refer to the same "
                    "underlying entity. Sits between the extracted-assertion layer (EntityMention) "
                    "and the optional curated layer (CanonicalEntity). Created non-destructively "
                    "by the entity resolution stage; raw mentions are never modified.\n\n"
                    "**Identity scoping**: ``cluster_id`` encodes ``run_id``, "
                    "``entity_type``, and ``normalized_text`` so that clusters are never "
                    "unintentionally merged across processing runs or entity types.  "
                    "``source_uri`` is intentionally **not** part of cluster identity — "
                    "mentions from different source documents within the same run that refer "
                    "to the same entity type and normalized text are considered the same "
                    "cluster, enabling cross-document clustering within a run.  "
                    "``source_uri`` is preserved as provenance on ``MEMBER_OF``, "
                    "``RESOLVES_TO``, and ``ALIGNED_WITH`` edges.  "
                    "Each component is percent-encoded (RFC 3986) before joining so that "
                    "a component containing the ``::`` delimiter cannot collide with a "
                    "legitimately different tuple.  Format: "
                    "``cluster::<run_id_enc>::<entity_type_enc>::<normalized_text_enc>``. "
                    "``entity_type=None`` is treated as an empty string before encoding, "
                    "producing an empty segment "
                    "(e.g. ``cluster::run1::::ibm`` when ``entity_type=None``)."
                ),
                properties=[
                    PropertyType(name="cluster_id", type="STRING", required=True),
                    PropertyType(name="canonical_name", type="STRING"),
                    PropertyType(name="normalized_text", type="STRING"),
                    PropertyType(name="entity_type", type="STRING"),
                    PropertyType(name="run_id", type="STRING"),
                    PropertyType(name="resolver_version", type="STRING"),
                    PropertyType(name="created_at", type="STRING"),
                ],
                additional_properties=True,
            ),
        ],
        relationship_types=[
            # Provisional resolution layer relationships
            RelationshipType(label="MEMBER_OF"),
            # Explicit candidate/review-queue relationships for ambiguous memberships.
            # Written alongside MEMBER_OF for "candidate" (abbreviation) and
            # "review_required" (borderline fuzzy) status edges so downstream
            # consumers can use them as a dedicated review queue without disturbing
            # the cluster membership graph.
            # Properties mirror MEMBER_OF: score, method, resolver_version, run_id,
            #   status ("candidate" | "review_required"), source_uri.
            RelationshipType(label="CANDIDATE_MATCH"),
            # Enrichment alignment: cluster → canonical (hybrid mode).
            # Properties: alignment_method, alignment_score, alignment_status,
            #   alignment_version, run_id, source_uri.
            # Created non-destructively; does not modify MEMBER_OF edges or cluster nodes.
            RelationshipType(label="ALIGNED_WITH"),
        ],
    )


__all__ = ["claim_extraction_schema", "claim_extraction_lexical_config", "resolution_layer_schema"]
