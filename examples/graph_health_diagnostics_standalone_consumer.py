from __future__ import annotations

import json
from pathlib import Path
from tempfile import TemporaryDirectory

from power_atlas.bootstrap import build_runtime_config, build_settings
from power_atlas.graph_health_diagnostics import run_graph_health_diagnostics


def _fake_query_rows_fetcher(*args: object, **kwargs: object) -> dict[str, list[dict[str, object]]]:
    return {
        "role_dist": [
            {"role": "subject", "total": 4},
            {"role": "object", "total": 4},
        ],
        "edge_coverage": [
            {"participant_edges": 0, "claim_count": 2},
            {"participant_edges": 1, "claim_count": 5},
            {"participant_edges": 2, "claim_count": 1},
        ],
        "match_method_dist": [
            {"match_method": "label_exact", "total": 4},
            {"match_method": "normalized_exact", "total": 3},
        ],
        "mention_clustering": [
            {"is_clustered": True, "mention_count": 9},
            {"is_clustered": False, "mention_count": 3},
        ],
        "cluster_size_dist": [
            {"member_count": 1, "cluster_count": 2},
            {"member_count": 2, "cluster_count": 2},
            {"member_count": 3, "cluster_count": 1},
        ],
        "cluster_type_frag": [
            {"distinct_types_in_cluster": 1, "cluster_count": 4},
            {"distinct_types_in_cluster": 2, "cluster_count": 1},
        ],
        "alignment_coverage": [
            {"is_aligned": True, "cluster_count": 4},
            {"is_aligned": False, "cluster_count": 1},
        ],
        "per_canonical": [
            {
                "canonical_entity": "Gamma Energy",
                "entity_id": "ORG10",
                "entity_type": "Organization",
                "aligned_cluster_count": 2,
                "bridged_mention_count": 4,
                "sample_methods": ["label_exact"],
            },
            {
                "canonical_entity": "Dana Price",
                "entity_id": "PER2",
                "entity_type": "Person",
                "aligned_cluster_count": 2,
                "bridged_mention_count": 5,
                "sample_methods": ["normalized_exact"],
            },
        ],
        "chain_health": [
            {
                "canonical_entity": "Gamma Energy",
                "entity_type": "Organization",
                "mention_count": 4,
                "claim_count": 3,
                "status": "active",
            },
            {
                "canonical_entity": "Dana Price",
                "entity_type": "Person",
                "mention_count": 5,
                "claim_count": 2,
                "status": "active",
            },
        ],
    }


def build_example_payload() -> dict[str, object]:
    with TemporaryDirectory() as temp_dir:
        output_dir = Path(temp_dir)
        settings = build_settings(
            {
                "NEO4J_URI": "bolt://localhost:7687",
                "NEO4J_USERNAME": "neo4j",
                "NEO4J_PASSWORD": "example-password",
                "NEO4J_DATABASE": "neo4j",
                "POWER_ATLAS_OUTPUT_DIR": str(output_dir),
            }
        )
        config = build_runtime_config(
            settings,
            dry_run=False,
            output_dir=output_dir,
        )

        result = run_graph_health_diagnostics(
            config,
            run_id="unstructured_ingest-20260514T000100Z-standalone",
            alignment_version="v2.0",
            query_rows_fetcher=_fake_query_rows_fetcher,
        )

        artifact_path = Path(result["artifact_path"])
        artifact = json.loads(artifact_path.read_text(encoding="utf-8"))
        return {
            "consumer": "graph_health_diagnostics_standalone_consumer",
            "alignment_version": result["alignment_version"],
            "artifact_relative_path": str(artifact_path.resolve().relative_to(output_dir.resolve())),
            "canonical_chain_entities": [
                row["canonical_entity"] for row in artifact["canonical_chain_health"]
            ],
            "run_id": result["run_id"],
            "status": result["status"],
            "summary": {
                "aligned_clusters": artifact["alignment_summary"]["aligned_clusters"],
                "alignment_coverage_pct": artifact["alignment_summary"]["alignment_coverage_pct"],
                "claim_coverage_pct": artifact["participation_summary"]["claim_coverage_pct"],
                "total_edges": artifact["participation_summary"]["total_edges"],
                "total_mentions": artifact["mention_summary"]["total_mentions"],
                "unclustered_mentions": artifact["mention_summary"]["unclustered_mentions"],
            },
            "warning_count": len(result["warnings"]),
        }


if __name__ == "__main__":
    print(json.dumps(build_example_payload(), sort_keys=True))