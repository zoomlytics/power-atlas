"""Reset the demo graph database to a clean state.

This script deletes only demo-owned graph content and drops only demo-owned
indexes.  It is safe to run against a dedicated demo database and is
idempotent: repeated runs succeed even when the graph is already empty or the
indexes no longer exist.

Demo-owned labels (nodes + all their relationships are removed):
  - Document, Chunk         (lexical layer written by ingest-pdf)
  - CanonicalEntity         (structured layer written by ingest-structured)
  - Claim                   (structured layer written by ingest-structured; claims.csv)
  - Fact                    (structured layer written by ingest-structured; facts.csv)
  - Relationship            (structured layer written by ingest-structured; relationships.csv)
  - Source                  (structured layer written by ingest-structured; dataset source nodes)
  - ExtractedClaim          (extraction layer written by extract-claims)
  - EntityMention           (extraction layer written by extract-claims)
  - UnresolvedEntity        (resolution layer written by resolve-entities; fallback for unresolved mentions)
  - ResolvedEntityCluster   (resolution layer written by resolve-entities; resolved entity clusters)

Stale participation edges (pre-v0.3 graphs only, non-migratable):
  Because the DETACH DELETE above removes all ExtractedClaim and EntityMention
  nodes, any v0.3 :HAS_PARTICIPANT edges attached to those nodes are
  automatically removed.

  Old demo graphs produced before v0.2 may contain :HAS_SUBJECT and :HAS_OBJECT
  edges (v0.1 types).  Old graphs produced before v0.3 may contain
  :HAS_SUBJECT_MENTION and :HAS_OBJECT_MENTION edges (v0.2 types).
  All of these relationship types are retired and replaced by :HAS_PARTICIPANT
  (v0.3).  In a clean, demo-owned database the DETACH DELETE of
  ExtractedClaim/EntityMention nodes is sufficient to remove these stale edges
  as a side-effect.  The script also issues explicit, scoped DELETE statements
  as a defense-in-depth / historic safety measure to clean up any such
  relationships that might remain between non-deleted or non-demo endpoints,
  and records the count in the reset report under
  ``stale_participation_edges_deleted``.

  **Old demo graphs (pre-v0.3) are not migratable.**  A full reset followed by
  a fresh pipeline run (ingest-pdf → extract-claims → resolve-entities) is the
  only supported path to a clean v0.3 graph.

Demo-owned indexes (dropped by name):
  - demo_chunk_embedding_index  (vector index on Chunk.embedding, created by
    ingest-pdf or run_demo.py setup; name pinned in
        demo/config/pdf_simple_kg_pipeline.yaml and power_atlas.contracts.pipeline)

Preserved (not touched by this script):
  - Any nodes with labels not in the list above
  - Relationships whose endpoints are not among the deleted demo nodes (regardless
    of relationship type); relationships attached to deleted nodes are removed via
    DETACH DELETE as a consequence of node deletion
  - Any indexes not in the list above
  - Any other Neo4j databases on the same server

Reset actions are written to a JSON report file in the output directory for
inspection/debugging.  See ``run_reset()`` for the report schema.
"""
from __future__ import annotations

import argparse
import logging
from pathlib import Path

from power_atlas.bootstrap import AppBaseline, build_app_context, create_neo4j_driver
from power_atlas.interfaces.cli.reset_demo_entrypoint import run_reset_demo_main
from power_atlas.interfaces.cli.reset_demo_support import (
    build_reset_settings_from_args as _build_reset_settings_from_args_impl,
    parse_reset_demo_args as _parse_reset_demo_args_impl,
)
from power_atlas.contracts import ARTIFACTS_DIR
from power_atlas.contracts.pipeline import PipelineContractSnapshot
from power_atlas.neo4j_io import validate_cypher_identifier as _validate_cypher_identifier
from power_atlas.reset_demo_runtime import DEMO_NODE_LABELS
from power_atlas.reset_demo_runtime import demo_owned_indexes as _demo_owned_indexes_impl
from power_atlas.reset_demo_runtime import run_reset

logger = logging.getLogger(__name__)



def _demo_owned_indexes(pipeline_contract):
    return _demo_owned_indexes_impl(pipeline_contract)


def parse_args(
  argv: list[str] | None = None,
  *,
  app_baseline: AppBaseline | None = None,
) -> argparse.Namespace:
    return _parse_reset_demo_args_impl(
        argv,
        demo_node_labels=DEMO_NODE_LABELS,
        demo_owned_indexes_resolver=_demo_owned_indexes,
        default_output_dir=ARTIFACTS_DIR,
    app_baseline=app_baseline,
    )


def _build_settings_from_args(
  args: argparse.Namespace,
  *,
  app_baseline: AppBaseline | None = None,
):
    return _build_reset_settings_from_args_impl(
        args,
    app_baseline=app_baseline,
    )


def main() -> None:
    run_reset_demo_main(
        parse_args=parse_args,
        build_settings_from_args=_build_settings_from_args,
        build_app_context=build_app_context,
        create_neo4j_driver=create_neo4j_driver,
        run_reset=run_reset,
    )


if __name__ == "__main__":
    main()
