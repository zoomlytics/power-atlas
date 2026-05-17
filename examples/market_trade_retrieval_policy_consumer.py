from __future__ import annotations

import json

from power_atlas.bootstrap import build_app_context, build_request_context, resolve_app_baseline
from power_atlas.contracts import RetrievalPolicy
from power_atlas.policy_packs import MARKET_TRADE_RETRIEVAL_POLICY
from power_atlas.retrieval_request_context_adapters import run_retrieval_request_context


def build_example_payload() -> dict[str, object]:
    app_context = build_app_context(
        environ={},
        app_baseline=resolve_app_baseline(retrieval_policy=MARKET_TRADE_RETRIEVAL_POLICY),
    )
    request_context = build_request_context(
        app_context,
        command="ask",
        dry_run=True,
        question="Which market/trade retrieval policy was forwarded?",
        run_id="market-trade-run-id",
        source_uri="file:///market/trade/source.pdf",
    )

    def _run_impl(config: object, **kwargs: object) -> dict[str, object]:
        retrieval_policy = kwargs["retrieval_policy"]
        assert isinstance(retrieval_policy, RetrievalPolicy)
        return {
            "consumer": "market_trade_retrieval_policy_consumer",
            "question": kwargs["question"],
            "run_id": kwargs["run_id"],
            "source_uri": kwargs["source_uri"],
            "all_runs": kwargs["all_runs"],
            "qa_prompt_id": retrieval_policy.qa_prompt_id,
            "ontology": {
                "claim_label": retrieval_policy.ontology.claim_label,
                "canonical_label": retrieval_policy.ontology.canonical_label,
                "mentioned_in_relationship": retrieval_policy.ontology.mentioned_in_relationship,
            },
            "traversal_defaults": {
                "expand_graph": retrieval_policy.default_expand_graph,
                "cluster_aware": retrieval_policy.default_cluster_aware,
            },
        }

    return run_retrieval_request_context(
        request_context,
        top_k=4,
        index_name=None,
        question=None,
        expand_graph=None,
        cluster_aware=None,
        message_history=None,
        interactive=False,
        run_impl=_run_impl,
    )


if __name__ == "__main__":
    print(json.dumps(build_example_payload(), sort_keys=True))