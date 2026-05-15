from __future__ import annotations

import json
from pathlib import Path
from tempfile import TemporaryDirectory

from power_atlas.bootstrap import build_app_context, build_request_context
from power_atlas.graph_health_diagnostics import run_graph_health_diagnostics_request_context


def _fake_query_rows_fetcher(*args: object, **kwargs: object) -> dict[str, list[dict[str, object]]]:
    return {
        "role_dist": [
            {"role": "subject", "total": 6},
            {"role": "object", "total": 3},
        ],
        "edge_coverage": [
            {"participant_edges": 0, "claim_count": 1},
            {"participant_edges": 1, "claim_count": 7},
            {"participant_edges": 2, "claim_count": 2},
        ],
        "match_method_dist": [
            {"match_method": "normalized_exact", "total": 5},
            {"match_method": "alias_split", "total": 2},
        ],
        "mention_clustering": [
            {"is_clustered": True, "mention_count": 10},
            {"is_clustered": False, "mention_count": 2},
        ],
        "cluster_size_dist": [
            {"member_count": 1, "cluster_count": 1},
            {"member_count": 2, "cluster_count": 3},
            {"member_count": 3, "cluster_count": 2},
        ],
        "cluster_type_frag": [
            {"distinct_types_in_cluster": 1, "cluster_count": 5},
            {"distinct_types_in_cluster": 2, "cluster_count": 1},
        ],
        "alignment_coverage": [
            {"is_aligned": True, "cluster_count": 5},
            {"is_aligned": False, "cluster_count": 1},
        ],
        "per_canonical": [
            {
                "canonical_entity": "Acme Corp",
                "entity_id": "ORG1",
                "entity_type": "Organization",
                "aligned_cluster_count": 3,
                "bridged_mention_count": 6,
                "sample_methods": ["normalized_exact"],
            },
            {
                "canonical_entity": "Beta Logistics",
                "entity_id": "ORG2",
                "entity_type": "Organization",
                "aligned_cluster_count": 2,
                "bridged_mention_count": 3,
                "sample_methods": ["alias_split"],
            },
        ],
        "chain_health": [
            {
                "canonical_entity": "Acme Corp",
                "entity_type": "Organization",
                "mention_count": 6,
                "claim_count": 4,
                "status": "active",
            },
            {
                "canonical_entity": "Beta Logistics",
                "entity_type": "Organization",
                "mention_count": 3,
                "claim_count": 2,
                "status": "active",
            },
        ],
    }


def build_example_payload() -> dict[str, object]:
    with TemporaryDirectory() as temp_dir:
        output_dir = Path(temp_dir)
        app_context = build_app_context(
            environ={
                "NEO4J_URI": "bolt://localhost:7687",
                "NEO4J_USERNAME": "neo4j",
                "NEO4J_PASSWORD": "example-password",
                "NEO4J_DATABASE": "neo4j",
                "POWER_ATLAS_OUTPUT_DIR": str(output_dir),
            }
        )
        request_context = build_request_context(
            app_context,
            command="graph-health",
            dry_run=False,
            run_id="unstructured_ingest-20260514T000000Z-example",
        )

        result = run_graph_health_diagnostics_request_context(
            request_context,
            alignment_version="v1.0",
            query_rows_fetcher=_fake_query_rows_fetcher,
        )

        artifact_path = Path(result["artifact_path"])
        artifact = json.loads(artifact_path.read_text(encoding="utf-8"))
        return {
            "consumer": "graph_health_diagnostics_consumer",
            "alignment_version": result["alignment_version"],
            "artifact_relative_path": str(artifact_path.resolve().relative_to(output_dir.resolve())),
            "canonical_chain_entities": [
                row["canonical_entity"] for row in artifact["canonical_chain_health"]
            ],
            "entity_type_policy_synonyms": {
                "Company": request_context.policies.entity_type_normalization.synonyms["Company"],
                "person": request_context.policies.entity_type_normalization.synonyms["person"],
            },
            "run_id": result["run_id"],
            "status": result["status"],
            "summary": {
                "aligned_clusters": artifact["alignment_summary"]["aligned_clusters"],
                "claim_coverage_pct": artifact["participation_summary"]["claim_coverage_pct"],
                "total_clusters": artifact["alignment_summary"]["total_clusters"],
                "total_edges": artifact["participation_summary"]["total_edges"],
                "total_mentions": artifact["mention_summary"]["total_mentions"],
                "unclustered_mentions": artifact["mention_summary"]["unclustered_mentions"],
            },
            "warning_count": len(result["warnings"]),
        }


if __name__ == "__main__":
    print(json.dumps(build_example_payload(), sort_keys=True))