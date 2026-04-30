"""Post-hybrid retrieval benchmark script.

Connects to a running Neo4j instance, runs the full retrieval benchmark defined
in ``demo/stages/retrieval_benchmark.py``, and writes a JSON artifact to
``<output-dir>/runs/<run_id>/retrieval_benchmark/`` when ``--run-id`` is provided,
or to ``<output-dir>/runs/retrieval_benchmark/`` when it is omitted.  The default
``<output-dir>`` is ``pipelines/`` (the directory containing this script's parent
directory); pass ``--output-dir`` to override it.

.. note::
    **Orchestrated runs:** the ``ingest`` orchestrator (``python -m demo.run_demo ingest``)
    automatically invokes ``run_retrieval_benchmark`` at the end of every batch run
    (after hybrid alignment), scoped to the active dataset, unstructured run, and
    ``alignment_version`` passed forward from the hybrid stage. This prevents
    cross-version aggregation when alignment is rerun for the same ``run_id`` and is
    material to reproducibility of the artifact. The artifact is written under
    ``<output-dir>/runs/<unstructured_run_id>/retrieval_benchmark/`` and included in
    the batch manifest under ``stages.retrieval_benchmark``.

    This standalone script is for **manual / standalone** benchmark runs against an
    existing graph — for example, to re-evaluate a previous run, to scope a benchmark
    to a different ``--dataset-id``, or to produce a baseline artifact without running
    the full pipeline.  Always pass ``--dataset-id`` in a multi-dataset graph to prevent
    shared entity names from matching canonical nodes across datasets.

The benchmark covers five canonical case types:

1. ``single_entity`` — single-entity canonical traversal (MercadoLibre, Xapo,
   Endeavor, Linda Rottenberg).
2. ``pairwise_entity`` — pairwise canonical claim lookup (Amazon ↔ eBay).
3. ``fragmented_entity`` — entities known to fragment under raw cluster-name
   traversal.
4. ``composite_claim`` — entities with list-valued claim slots.
5. ``canonical_vs_cluster`` — side-by-side claim-count comparison.

For each case the artifact records the canonical traversal rows, the parallel
cluster-name traversal rows, the full lower-layer chain inspection rows, and
derived fragmentation metrics.

Dataset scoping
---------------
Use ``--dataset-id`` to scope all ``CanonicalEntity`` lookups to a specific
dataset.  In a multi-dataset graph this prevents shared entity names from
matching canonical nodes across datasets (e.g. an entity present in both
``demo_dataset_v1`` and ``demo_dataset_v2`` would otherwise be counted twice).
The ``dataset_id`` is stamped as a top-level field in the artifact.

Omit ``--dataset-id`` to aggregate across all datasets — suitable for quick
explorations but not for regression baselines in a multi-dataset graph.

Usage
-----
Set Neo4j connection env vars (or pass via CLI flags), then run:

    # Scoped to a specific dataset, run, and alignment version
    python pipelines/query/retrieval_benchmark.py \\
        --dataset-id demo_dataset_v1 \\
        --run-id unstructured_ingest-20240101T000000000000Z-abcd1234 \\
        --alignment-version v1.0

    # Unscoped — aggregates across all runs and datasets
    python pipelines/query/retrieval_benchmark.py

Environment variables
---------------------
NEO4J_URI       (default: bolt://localhost:7687)
NEO4J_USERNAME  (default: neo4j)
NEO4J_PASSWORD  (required)
NEO4J_DATABASE  (default: neo4j)
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

# Ensure the repository root is on sys.path when run as a script.
_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from power_atlas.bootstrap import build_runtime_config, build_settings  # noqa: E402
from power_atlas.interfaces.cli.retrieval_benchmark_support import (  # noqa: E402
    build_retrieval_benchmark_cli_request_context as _build_retrieval_benchmark_cli_request_context_impl,
    parse_retrieval_benchmark_args as _parse_retrieval_benchmark_args_impl,
)
from power_atlas.interfaces.cli.retrieval_benchmark_entrypoint import (  # noqa: E402
    run_retrieval_benchmark_main,
)
from demo.stages.retrieval_benchmark import run_retrieval_benchmark_request_context  # noqa: E402

# Base output directory — the parent of `runs/`, matching Config.output_dir conventions.
_PIPELINES_DIR = Path(__file__).resolve().parent.parent

_logger = logging.getLogger(__name__)


def _build_cli_request_context(args: argparse.Namespace):
    return _build_retrieval_benchmark_cli_request_context_impl(
        args,
    )


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    return _parse_retrieval_benchmark_args_impl(
        argv,
        default_output_dir=_PIPELINES_DIR,
        doc_epilog=__doc__,
    )


def main(argv: list[str] | None = None) -> None:
    run_retrieval_benchmark_main(
        parse_args=_parse_args,
        build_cli_request_context=_build_cli_request_context,
        run_retrieval_benchmark_request_context=run_retrieval_benchmark_request_context,
        warn=lambda warning: _logger.warning("%s", warning),
        argv=argv,
    )


if __name__ == "__main__":
    main()
