from __future__ import annotations

import json
import re

from power_atlas.bootstrap import build_app_context, build_request_context
from power_atlas.contracts import (
    EntityResolutionAlignmentContract,
    EntityResolutionAlignmentStep,
    EntityResolutionCanonicalLookupContract,
    EntityResolutionDatasetSelectionContract,
    EntityResolutionGraphContract,
)
from power_atlas.entity_resolution_entrypoint import (
    RESOLUTION_MODE_HYBRID,
    run_entity_resolution,
    run_entity_resolution_request_context,
)


def build_example_payload() -> dict[str, object]:
    graph_contract = EntityResolutionGraphContract(
        mention_label="SecurityMention",
        canonical_label="Security",
        cluster_label="SecurityCluster",
        resolves_to_relationship="RESOLVES_TO_SECURITY",
        member_of_relationship="MEMBER_OF_SECURITY_CLUSTER",
        candidate_match_relationship="CANDIDATE_SECURITY_MATCH",
        aligned_with_relationship="ALIGNED_WITH_SECURITY",
    )
    canonical_lookup = EntityResolutionCanonicalLookupContract(
        canonical_entity_id_field="security_id",
        canonical_run_id_field="security_run_id",
        canonical_name_field="security_name",
        canonical_aliases_field="ticker_aliases",
        qid_pattern=re.compile(r"^SEC\d+$"),
        qid_exact_method="security_id_exact",
        label_exact_method="security_label_exact",
        alias_exact_method="ticker_alias_exact",
        unresolved_method="security_cluster",
        aligned_status="tentative",
    )
    alignment_contract = EntityResolutionAlignmentContract(
        steps=(
            EntityResolutionAlignmentStep(
                lookup_table="alias",
                cluster_keys=lambda cluster: (cluster["normalized_text"].lstrip("$"),),
                method="ticker_symbol_alias",
                score=0.97,
                status="tentative",
            ),
            EntityResolutionAlignmentStep(
                lookup_table="label",
                method="security_label_exact",
                score=0.9,
                status="aligned",
            ),
        )
    )
    dataset_selection = EntityResolutionDatasetSelectionContract(
        select_dataset_id=lambda config, dataset_id, dataset_name: (
            dataset_id
            or f"market-canonicals::{dataset_name or getattr(config, 'dataset_name', 'missing')}"
        )
    )

    app_context = build_app_context(
        environ={"POWER_ATLAS_DATASET": "market_trade_dataset_v1"}
    )
    request_context = build_request_context(
        app_context,
        command="resolve",
        dry_run=True,
        resolution_mode=RESOLUTION_MODE_HYBRID,
        run_id="market-trade-entity-resolution-run-id",
        source_uri="file:///market/trade/source.pdf",
    )

    def _runtime_runner(**kwargs: object) -> dict[str, object]:
        runtime_graph = kwargs["entity_resolution_graph"]
        runtime_lookup = kwargs["entity_resolution_canonical_lookup"]
        runtime_alignment = kwargs["entity_resolution_alignment"]
        assert isinstance(runtime_graph, EntityResolutionGraphContract)
        assert isinstance(runtime_lookup, EntityResolutionCanonicalLookupContract)
        assert isinstance(runtime_alignment, EntityResolutionAlignmentContract)
        return {
            "consumer": "market_trade_entity_resolution_consumer",
            "run_id": kwargs["run_id"],
            "source_uri": kwargs["source_uri"],
            "resolution_mode": kwargs["resolution_mode"],
            "effective_dataset_id": kwargs["effective_dataset_id"],
            "graph": {
                "canonical_label": runtime_graph.canonical_label,
                "member_of_relationship": runtime_graph.member_of_relationship,
                "aligned_with_relationship": runtime_graph.aligned_with_relationship,
            },
            "canonical_lookup": {
                "entity_id_field": runtime_lookup.canonical_entity_id_field,
                "aliases_field": runtime_lookup.canonical_aliases_field,
                "qid_exact_method": runtime_lookup.qid_exact_method,
            },
            "alignment_steps": [
                {
                    "lookup_table": step.lookup_table,
                    "method": step.method,
                    "score": step.score,
                    "status": step.status,
                }
                for step in runtime_alignment.steps
            ],
        }

    def _config_runner(config: object, **kwargs: object) -> dict[str, object]:
        return run_entity_resolution(
            config,
            runtime_runner=_runtime_runner,
            **kwargs,
        )

    return run_entity_resolution_request_context(
        request_context,
        resolution_mode=RESOLUTION_MODE_HYBRID,
        entity_resolution_dataset_selection=dataset_selection,
        entity_resolution_alignment=alignment_contract,
        entity_resolution_canonical_lookup=canonical_lookup,
        entity_resolution_graph=graph_contract,
        config_runner=_config_runner,
    )


if __name__ == "__main__":
    print(json.dumps(build_example_payload(), sort_keys=True))