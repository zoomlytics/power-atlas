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
        ],
    )


__all__ = ["claim_extraction_schema", "claim_extraction_lexical_config"]
