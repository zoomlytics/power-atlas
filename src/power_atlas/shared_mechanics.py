from __future__ import annotations

from dataclasses import dataclass
from importlib import import_module
from typing import Any, Literal


@dataclass(frozen=True)
class SharedMechanicsModuleRecord:
    module: str
    status: Literal["included", "deferred"]
    rationale: str
    hidden_assumptions: tuple[str, ...] = ()


@dataclass(frozen=True)
class SharedMechanicsPilotSurface:
    included_modules: tuple[SharedMechanicsModuleRecord, ...]
    deferred_modules: tuple[SharedMechanicsModuleRecord, ...]


SHARED_MECHANICS_PILOT = SharedMechanicsPilotSurface(
    included_modules=(
        SharedMechanicsModuleRecord(
            module="power_atlas.contracts.runtime",
            status="included",
            rationale=(
                "Runtime config carriers and run-id helpers are mechanics-heavy and do not own "
                "dataset-root or pipeline-default authority."
            ),
        ),
        SharedMechanicsModuleRecord(
            module="power_atlas.contracts.manifest",
            status="included",
            rationale=(
                "Manifest shaping and atomic write helpers are runtime support mechanics rather "
                "than Power Atlas dataset or policy surfaces."
            ),
        ),
        SharedMechanicsModuleRecord(
            module="power_atlas.neo4j_io",
            status="included",
            rationale=(
                "Identifier validation and low-level Neo4j IO helpers are reusable execution "
                "mechanics below current app route semantics."
            ),
        ),
        SharedMechanicsModuleRecord(
            module="power_atlas.run_scope_queries",
            status="included",
            rationale=(
                "Run-scope query helpers operate on explicit Neo4j settings and database inputs "
                "without owning repo fixture layout or dataset-root defaults."
            ),
        ),
        SharedMechanicsModuleRecord(
            module="power_atlas.retrieval_postprocessing",
            status="included",
            rationale=(
                "Answer citation postprocessing is string-and-hit shaping logic that does not own "
                "domain policy or app baseline defaults."
            ),
        ),
        SharedMechanicsModuleRecord(
            module="power_atlas.retrieval_request_helpers",
            status="included",
            rationale=(
                "Retrieval query-parameter and scope-label helpers are request-shaping mechanics "
                "independent of the current app dataset authority."
            ),
        ),
        SharedMechanicsModuleRecord(
            module="power_atlas.retrieval_runtime_bindings",
            status="included",
            rationale=(
                "Retrieval runtime binding now has a request-free helper layer below RequestContext, "
                "so execution binding can be consumed without app-owned context carriers."
            ),
        ),
    ),
    deferred_modules=(
        SharedMechanicsModuleRecord(
            module="power_atlas.context",
            status="deferred",
            rationale=(
                "Context carriers are not yet mechanics-only because they still bundle app policy, "
                "settings, and pipeline-contract ownership into the current RequestContext surface."
            ),
            hidden_assumptions=(
                "AppContext and RequestContext still depend on AppSettings-backed runtime state.",
                "Default app-policy construction is still coupled to the current Power Atlas policy set.",
            ),
        ),
        SharedMechanicsModuleRecord(
            module="power_atlas.retrieval_request_context_adapters",
            status="deferred",
            rationale=(
                "Request-context adapters remain above the mechanics boundary because their public "
                "API still requires the app-owned RequestContext surface, even though the lower-level "
                "execution binding now lives in power_atlas.retrieval_runtime_bindings."
            ),
            hidden_assumptions=(
                "The adapter API currently requires RequestContext from power_atlas.context.",
                "Only the lower-level execution binding is request-free; the adapter surface still belongs to the app-owned context layer.",
            ),
        ),
        SharedMechanicsModuleRecord(
            module="power_atlas.adapters.neo4j.*",
            status="deferred",
            rationale=(
                "The adapter family needs a narrower audit before grouping it wholesale because it "
                "still mixes clean query helpers with stage-specific runtime modules."
            ),
            hidden_assumptions=(
                "The current pilot includes run-scope query mechanics via power_atlas.run_scope_queries only.",
                "A broader adapters.neo4j family surface would currently mix mechanics with stage/domain runtime ownership.",
            ),
        ),
    ),
)


def get_shared_mechanics_pilot_surface() -> SharedMechanicsPilotSurface:
    return SHARED_MECHANICS_PILOT


_EXPORTS = {
    "CITATION_FALLBACK_PREFIX": (
        "power_atlas.retrieval_postprocessing",
        "CITATION_FALLBACK_PREFIX",
    ),
    "Config": ("power_atlas.contracts.runtime", "Config"),
    "build_batch_manifest": ("power_atlas.contracts.manifest", "build_batch_manifest"),
    "build_citation_fallback": (
        "power_atlas.retrieval_postprocessing",
        "build_citation_fallback",
    ),
    "build_retrieval_query_params": (
        "power_atlas.retrieval_request_helpers",
        "build_retrieval_query_params",
    ),
    "run_interactive_retrieval_with_runtime_inputs": (
        "power_atlas.retrieval_runtime_bindings",
        "run_interactive_retrieval_with_runtime_inputs",
    ),
    "run_retrieval_with_runtime_inputs": (
        "power_atlas.retrieval_runtime_bindings",
        "run_retrieval_with_runtime_inputs",
    ),
    "build_stage_manifest": ("power_atlas.contracts.manifest", "build_stage_manifest"),
    "check_all_answers_cited": (
        "power_atlas.retrieval_postprocessing",
        "check_all_answers_cited",
    ),
    "fetch_dataset_id_for_run": ("power_atlas.run_scope_queries", "fetch_dataset_id_for_run"),
    "fetch_latest_unstructured_run_id": (
        "power_atlas.run_scope_queries",
        "fetch_latest_unstructured_run_id",
    ),
    "first_citation_token_from_hits": (
        "power_atlas.retrieval_postprocessing",
        "first_citation_token_from_hits",
    ),
    "format_retrieval_scope_label": (
        "power_atlas.retrieval_request_helpers",
        "format_retrieval_scope_label",
    ),
    "make_run_id": ("power_atlas.contracts.runtime", "make_run_id"),
    "timestamp": ("power_atlas.contracts.runtime", "timestamp"),
    "write_manifest": ("power_atlas.contracts.manifest", "write_manifest"),
    "write_manifest_md": ("power_atlas.contracts.manifest", "write_manifest_md"),
}


__all__ = sorted(
    [
        "SHARED_MECHANICS_PILOT",
        "SharedMechanicsModuleRecord",
        "SharedMechanicsPilotSurface",
        "get_shared_mechanics_pilot_surface",
        *_EXPORTS.keys(),
    ]
)


def __getattr__(name: str) -> Any:
    if name in _EXPORTS:
        module_name, attr_name = _EXPORTS[name]
        value = getattr(import_module(module_name), attr_name)
        globals()[name] = value
        return value
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


def __dir__() -> list[str]:
    return sorted(list(globals().keys()) + __all__)