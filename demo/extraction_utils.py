from __future__ import annotations

from typing import Any

import neo4j
from neo4j_graphrag.experimental.components.types import LexicalGraphConfig, Neo4jGraph, TextChunk

from power_atlas.extraction_rows import prepare_extracted_rows as _prepare_extracted_rows_impl
from power_atlas.extraction_writes import write_all_extraction_data as _write_all_extraction_data_impl
from power_atlas.extraction_writes import write_extracted_rows as _write_extracted_rows_impl

# ---------------------------------------------------------------------------
# Private row-preparation helpers
# ---------------------------------------------------------------------------


def prepare_extracted_rows(
    *,
    graph: Neo4jGraph,
    text_chunks: list[TextChunk],
    run_id: str,
    source_uri: str | None,
    lexical_graph_config: LexicalGraphConfig,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[str]]:
    return _prepare_extracted_rows_impl(
        graph=graph,
        text_chunks=text_chunks,
        run_id=run_id,
        source_uri=source_uri,
        lexical_graph_config=lexical_graph_config,
    )

def write_extracted_rows(
    driver: neo4j.Driver,
    *,
    neo4j_database: str,
    lexical_graph_config: LexicalGraphConfig,
    claim_rows: list[dict[str, Any]],
    mention_rows: list[dict[str, Any]],
) -> None:
    _write_extracted_rows_impl(
        driver,
        neo4j_database=neo4j_database,
        lexical_graph_config=lexical_graph_config,
        claim_rows=claim_rows,
        mention_rows=mention_rows,
    )


def write_all_extraction_data(
    driver: neo4j.Driver,
    *,
    neo4j_database: str,
    lexical_graph_config: LexicalGraphConfig,
    claim_rows: list[dict[str, Any]],
    mention_rows: list[dict[str, Any]],
    edge_rows: list[dict[str, Any]],
) -> None:
    """Write claims, mentions, and participation edges in a single transaction.

    Uses ``session.execute_write`` so that all three write operations (claims,
    mentions, participation edges) either all succeed or all roll back.
    This prevents the partial-write state where claims/mentions exist in the
    graph but their ``HAS_PARTICIPANT`` edges are missing (v0.3 model).

    Prefer this function over calling :func:`write_extracted_rows` and
    :func:`~demo.stages.claim_participation.write_participation_edges`
    separately whenever you hold both in-memory row lists at the same time.

    Parameters
    ----------
    driver:
        An open :class:`neo4j.Driver` instance.
    neo4j_database:
        Neo4j database name (e.g. ``"neo4j"``).
    lexical_graph_config:
        Lexical graph configuration used to validate and resolve the chunk
        node label and chunk-id property name.
    claim_rows:
        Rows produced by :func:`prepare_extracted_rows` for ``ExtractedClaim``
        nodes.
    mention_rows:
        Rows produced by :func:`prepare_extracted_rows` for ``EntityMention``
        nodes.
    edge_rows:
        Edge rows produced by
        :func:`~demo.stages.claim_participation.build_participation_edges`.
    """
    _write_all_extraction_data_impl(
        driver,
        neo4j_database=neo4j_database,
        lexical_graph_config=lexical_graph_config,
        claim_rows=claim_rows,
        mention_rows=mention_rows,
        edge_rows=edge_rows,
    )
