"""Graph-health diagnostics script.

Connects to a running Neo4j instance, runs the full set of graph-health
diagnostic queries defined in ``demo/stages/graph_health.py``, and writes
a JSON artifact to ``pipelines/runs/<run_id>/graph_health/`` when
``--run-id`` is provided, or to ``pipelines/runs/graph_health/`` when it is
omitted.

When no ``--run-id`` is given the queries aggregate across **all** runs
in the database (useful for a quick whole-database health check).

Usage
-----
Set Neo4j connection env vars (or pass via CLI flags), then run:

    # Scoped to a specific run and alignment version
    python pipelines/query/graph_health_diagnostics.py \\
        --run-id unstructured_ingest-20240101T000000000000Z-abcd1234 \\
        --alignment-version v1.0

    # Unscoped — aggregates across all runs
    python pipelines/query/graph_health_diagnostics.py

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
from power_atlas.interfaces.cli.graph_health_diagnostics_support import (  # noqa: E402
    build_graph_health_cli_request_context as _build_graph_health_cli_request_context_impl,
    parse_graph_health_diagnostics_args as _parse_graph_health_diagnostics_args_impl,
)
from power_atlas.interfaces.cli.graph_health_diagnostics_entrypoint import (  # noqa: E402
    run_graph_health_diagnostics_main,
)
from demo.stages.graph_health import run_graph_health_diagnostics_request_context  # noqa: E402

# Base output directory — the parent of `runs/`, matching Config.output_dir conventions.
# Artifacts land in <_PIPELINES_DIR>/runs/<run_id>/graph_health/ by default.
_PIPELINES_DIR = Path(__file__).resolve().parent.parent

_logger = logging.getLogger(__name__)


def _build_cli_request_context(args: argparse.Namespace):
    return _build_graph_health_cli_request_context_impl(
        args,
    )


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    return _parse_graph_health_diagnostics_args_impl(
        argv,
        default_output_dir=_PIPELINES_DIR,
        doc_epilog=__doc__,
    )


def main(argv: list[str] | None = None) -> None:
    run_graph_health_diagnostics_main(
        parse_args=_parse_args,
        build_cli_request_context=_build_cli_request_context,
        run_graph_health_diagnostics_request_context=run_graph_health_diagnostics_request_context,
        warn=lambda warning: _logger.warning("%s", warning),
        argv=argv,
    )


if __name__ == "__main__":
    main()
