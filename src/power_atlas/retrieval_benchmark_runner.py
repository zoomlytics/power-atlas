from __future__ import annotations

import dataclasses
import json
import logging
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from power_atlas.retrieval_benchmark_queries import Q_CANONICAL_SINGLE as _Q_CANONICAL_SINGLE
from power_atlas.retrieval_benchmark_queries import Q_CATALOG_EXISTENCE_CHECK as _Q_CATALOG_EXISTENCE_CHECK
from power_atlas.retrieval_benchmark_queries import Q_LOWER_LAYER_CHAIN as _Q_LOWER_LAYER_CHAIN
from power_atlas.retrieval_benchmark_queries import Q_PAIRWISE_CANONICAL as _Q_PAIRWISE_CANONICAL
from power_atlas.retrieval_benchmark_queries import build_pairwise_query_specs
from power_atlas.retrieval_benchmark_queries import build_single_entity_query_specs
from power_atlas.retrieval_benchmark_queries import fetch_retrieval_benchmark_query_rows
from power_atlas.settings import Neo4jSettings

_logger = logging.getLogger(__name__)


@dataclasses.dataclass(frozen=True)
class BenchmarkCaseDefinition:
    case_id: str
    case_type: str
    entity_names: tuple[str, ...]
    description: str
    expected_shape: str
    failure_modes: tuple[str, ...]
    lower_layer_checks: tuple[str, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "entity_names", tuple(self.entity_names))
        object.__setattr__(self, "failure_modes", tuple(self.failure_modes))
        object.__setattr__(self, "lower_layer_checks", tuple(self.lower_layer_checks))


BENCHMARK_CASES: list[BenchmarkCaseDefinition] = [
    BenchmarkCaseDefinition(
        case_id="mercadolibre_single",
        case_type="single_entity",
        entity_names=["mercadolibre"],
        description=(
            "Single-entity canonical traversal for MercadoLibre. "
            "Exercises the canonical -> cluster -> mention -> claim path for a "
            "well-known organization that may appear under multiple surface forms."
        ),
        expected_shape=(
            "At least one row with canonical_entity='MercadoLibre', one or more "
            "distinct cluster values, and claims with role='subject' or role='object'. "
            "The canonical path should return a single canonical_entity value with "
            "claims deduplicated across surface-form variants."
        ),
        failure_modes=[
            "canonical_rows empty - CanonicalEntity not present or ALIGNED_WITH edges missing",
            "lower_layer_rows shows cluster with zero claims - participation stage gap",
            "fragmentation_detected - cluster-name path returns more clusters than canonical",
        ],
        lower_layer_checks=[
            "canonical -> cluster: verify ALIGNED_WITH edges present",
            "cluster -> mention: verify MEMBER_OF edges present",
            "mention -> claim: verify HAS_PARTICIPANT edges present",
        ],
    ),
    BenchmarkCaseDefinition(
        case_id="xapo_single",
        case_type="single_entity",
        entity_names=["xapo"],
        description=(
            "Single-entity canonical traversal for Xapo. "
            "Tests retrieval for a fintech entity that may appear under "
            "abbreviated and full-name surface forms."
        ),
        expected_shape=(
            "Rows with canonical_entity containing 'Xapo', claims grouped under "
            "a single canonical entry point regardless of surface-form variation."
        ),
        failure_modes=[
            "canonical_rows empty - Xapo not in structured catalog or alignment failed",
            "cluster_rows returns zero results - entity not mentioned in unstructured source",
            "multiple canonical_entity values - duplicate CanonicalEntity nodes",
        ],
        lower_layer_checks=[
            "canonical -> cluster: verify ALIGNED_WITH edges present",
            "cluster -> mention: verify MEMBER_OF edges present",
        ],
    ),
    BenchmarkCaseDefinition(
        case_id="endeavor_single",
        case_type="single_entity",
        entity_names=["endeavor"],
        description=(
            "Single-entity canonical traversal for Endeavor. "
            "Tests retrieval for a known entity present in the structured "
            "catalog and likely mentioned in unstructured sources."
        ),
        expected_shape=(
            "Rows with canonical_entity containing 'Endeavor', at least one "
            "participating mention, and at least one associated claim."
        ),
        failure_modes=[
            "canonical_rows empty - Endeavor not in structured catalog",
            "lower_layer_rows shows zero claims - participation coverage gap",
        ],
        lower_layer_checks=[
            "canonical -> cluster: verify ALIGNED_WITH edges present",
            "mention -> claim: verify HAS_PARTICIPANT edges present",
        ],
    ),
    BenchmarkCaseDefinition(
        case_id="linda_rottenberg_single",
        case_type="single_entity",
        entity_names=["linda rottenberg"],
        description=(
            "Single-entity canonical traversal for Linda Rottenberg (Person). "
            "Tests retrieval for a named individual, verifying the person-entity "
            "path works symmetrically with org-entity cases."
        ),
        expected_shape=(
            "Rows with canonical_entity containing 'Linda Rottenberg', entity_type='Person', "
            "claims where she appears as subject or object."
        ),
        failure_modes=[
            "canonical_rows empty - Linda Rottenberg not in structured catalog",
            "entity_type mismatch - mention clustered as Organization instead of Person",
            "lower_layer_rows shows cluster with zero claims",
        ],
        lower_layer_checks=[
            "canonical -> cluster: verify ALIGNED_WITH edges present with entity_type='Person'",
            "cluster -> mention: verify MEMBER_OF edges present",
            "mention -> claim: verify HAS_PARTICIPANT edges present",
        ],
    ),
    BenchmarkCaseDefinition(
        case_id="amazon_ebay_pairwise",
        case_type="pairwise_entity",
        entity_names=["amazon", "ebay"],
        description=(
            "Pairwise canonical claim lookup for Amazon and eBay. "
            "Finds claims where both entities appear as participants (subject "
            "and/or object), verifying that pairwise canonical resolution works "
            "for two distinct organization entities."
        ),
        expected_shape=(
            "Zero or more rows each carrying both subject_canonical and object_canonical "
            "resolved to the correct canonical entities. Zero rows is acceptable if "
            "no cross-entity claims were extracted; what matters is the query returns "
            "without error and the canonical chain is traversable for both entities."
        ),
        failure_modes=[
            "query returns error - ALIGNED_WITH or MEMBER_OF edges missing for one entity",
            "result mixes unrelated entities - toLower CONTAINS filter too broad",
        ],
        lower_layer_checks=[
            "single-entity lower_layer check for each entity separately before pairwise",
        ],
    ),
    BenchmarkCaseDefinition(
        case_id="mercadolibre_fragmentation",
        case_type="fragmented_entity",
        entity_names=["mercadolibre"],
        description=(
            "Fragmentation check for MercadoLibre. "
            "Compares the number of distinct clusters returned by cluster-name "
            "traversal vs. canonical traversal. MercadoLibre is a known candidate "
            "for entity-type splits (e.g., appearing as both Organization and Person "
            "clusters under the same name text)."
        ),
        expected_shape=(
            "Canonical traversal returns a single canonical_entity value. "
            "Cluster-name traversal may return multiple rows if fragmentation "
            "exists; fragmentation_detected=True is the expected failure signal."
        ),
        failure_modes=[
            "fragmentation_detected=True - cluster-name returns more clusters than canonical",
            "canonical_rows empty - CanonicalEntity not present",
        ],
        lower_layer_checks=[
            "fragmentation_check_rows: inspect cluster_entity_type distribution",
            "canonical -> cluster: confirm single aligned canonical entity",
        ],
    ),
    BenchmarkCaseDefinition(
        case_id="endeavor_composite",
        case_type="composite_claim",
        entity_names=["endeavor"],
        description=(
            "Composite/list-valued claim case for Endeavor. "
            "Looks for claims where the subject or object slot contains a "
            "list-valued expression (joined by 'and', 'or', '/', etc.) that "
            "was resolved via the list-split match path. This exercises the "
            "claim_participation list-split fallback."
        ),
        expected_shape=(
            "Rows where match_method='list_split' appear in canonical_rows or "
            "cluster_rows, or match_method='normalized_exact' for sub-tokens. "
            "If no list-split edges exist for this entity, the case is informative "
            "rather than a failure."
        ),
        failure_modes=[
            "match_method only shows raw_exact - list-split path was not exercised",
            "canonical_rows empty - Endeavor not reachable via canonical path",
        ],
        lower_layer_checks=[
            "canonical -> cluster -> mention -> claim: inspect match_method per row",
            "check participation_metrics.json for list_split_suppressed count",
        ],
    ),
    BenchmarkCaseDefinition(
        case_id="xapo_canonical_vs_cluster",
        case_type="canonical_vs_cluster",
        entity_names=["xapo"],
        description=(
            "Canonical-traversal vs. cluster-name-traversal comparison for Xapo. "
            "Records the claim counts and cluster counts from both paths so that "
            "the delta can be tracked as a regression metric."
        ),
        expected_shape=(
            "canonical_claim_count >= cluster_claim_count (canonical deduplicates) or "
            "both counts equal (no fragmentation). "
            "cluster_name_cluster_count >= canonical_cluster_count (fragmentation is additive). "
            "fragmentation_detected=False is the healthy state."
        ),
        failure_modes=[
            "canonical_claim_count < cluster_claim_count - canonical path misses claims "
            "(investigate ALIGNED_WITH coverage; if canonical rows are entirely absent see catalog_present_canonical_empty hint)",
            "fragmentation_detected=True - cluster-name path returns spurious extra clusters",
        ],
        lower_layer_checks=[
            "canonical -> cluster: inspect ALIGNED_WITH edges for alignment_method",
            "fragmentation_check_rows: entity_type distribution across clusters",
        ],
    ),
    BenchmarkCaseDefinition(
        case_id="linda_rottenberg_canonical_vs_cluster",
        case_type="canonical_vs_cluster",
        entity_names=["linda rottenberg"],
        description=(
            "Canonical-traversal vs. cluster-name-traversal comparison for Linda Rottenberg. "
            "Validates that Person-type entities also benefit from canonical deduplication."
        ),
        expected_shape=(
            "canonical_claim_count >= cluster_claim_count. "
            "fragmentation_detected=False is the healthy state for a named individual."
        ),
        failure_modes=[
            "fragmentation_detected=True - entity_type split produced both Person and Org clusters",
            "canonical_rows empty - Linda Rottenberg not in structured catalog",
        ],
        lower_layer_checks=[
            "canonical -> cluster: verify entity_type='Person' on aligned cluster",
            "fragmentation_check_rows: confirm single entity_type across clusters",
        ],
    ),
]


def _records_to_dicts(records: list[Any]) -> list[dict[str, Any]]:
    return [dict(r) for r in records]


def _count_distinct(rows: list[dict[str, Any]], key: str) -> int:
    return len({row[key] for row in rows if row.get(key) is not None})


def _count_distinct_claims(rows: list[dict[str, Any]]) -> int:
    return _count_distinct(rows, "claim_id")


def _count_distinct_clusters(rows: list[dict[str, Any]]) -> int:
    if any("cluster_id" in row for row in rows):
        return _count_distinct(rows, "cluster_id")
    return _count_distinct(rows, "cluster")


def _detect_fragmentation(
    canonical_cluster_count: int,
    cluster_name_cluster_count: int,
) -> bool:
    return cluster_name_cluster_count > canonical_cluster_count


def _classify_fragmentation_type(
    fragmentation_check_rows: list[dict[str, Any]],
    canonical_rows: list[dict[str, Any]],
    cluster_rows: list[dict[str, Any]],
    catalog_check_rows: list[dict[str, Any]] | None = None,
) -> list[str]:
    hints: list[str] = []
    entity_types = [
        row.get("entity_type")
        for row in fragmentation_check_rows
        if row.get("entity_type") is not None
    ]
    unique_types = set(entity_types)
    unique_lower = {entity_type.lower() for entity_type in unique_types}
    if len(unique_lower) < len(unique_types):
        hints.append("entity_type_case_split")

    if not canonical_rows and cluster_rows:
        if catalog_check_rows is None:
            hints.append("catalog_absent_or_alignment_gap")
        elif catalog_check_rows:
            hints.append("catalog_present_canonical_empty")
        else:
            hints.append("catalog_absent")

    return hints


@dataclasses.dataclass
class BenchmarkCaseResult:
    case_id: str
    case_type: str
    entity_names: list[str]
    description: str
    expected_shape: str
    failure_modes: list[str]
    canonical_rows: list[dict[str, Any]]
    cluster_rows: list[dict[str, Any]]
    lower_layer_rows: list[dict[str, Any]]
    fragmentation_check_rows: list[dict[str, Any]]
    canonical_claim_count: int
    cluster_claim_count: int
    canonical_cluster_count: int
    cluster_name_cluster_count: int
    fragmentation_detected: bool
    canonical_empty_cluster_populated: bool
    fragmentation_type_hints: list[str]
    catalog_check_rows: list[dict[str, Any]]
    canonical_catalog_present: bool

    def to_dict(self) -> dict[str, Any]:
        return dataclasses.asdict(self)


@dataclasses.dataclass
class PairwiseCaseResult:
    case_id: str
    entity_names: list[str]
    description: str
    expected_shape: str
    failure_modes: list[str]
    pairwise_rows: list[dict[str, Any]]
    pairwise_claim_count: int

    def to_dict(self) -> dict[str, Any]:
        return dataclasses.asdict(self)


@dataclasses.dataclass
class RetrievalBenchmarkArtifact:
    generated_at: str
    run_id: str | None
    dataset_id: str | None
    alignment_version: str | None
    case_results: list[dict[str, Any]]
    pairwise_results: list[dict[str, Any]]
    benchmark_summary: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return dataclasses.asdict(self)

    def to_json(self, *, indent: int = 2) -> str:
        return json.dumps(self.to_dict(), indent=indent)


def _compute_benchmark_summary(
    case_results: list[BenchmarkCaseResult],
    pairwise_results: list[PairwiseCaseResult],
) -> dict[str, Any]:
    total_cases = len(case_results) + len(pairwise_results)
    fragmentation_detected_count = sum(1 for result in case_results if result.fragmentation_detected)
    entities_with_claims_canonical = sum(1 for result in case_results if result.canonical_claim_count > 0)
    entities_with_claims_cluster = sum(1 for result in case_results if result.cluster_claim_count > 0)
    total_canonical_claims = sum(result.canonical_claim_count for result in case_results)
    total_cluster_claims = sum(result.cluster_claim_count for result in case_results)
    total_pairwise_claims = sum(result.pairwise_claim_count for result in pairwise_results)
    canonical_empty_cluster_populated_count = sum(
        1 for result in case_results if result.canonical_empty_cluster_populated
    )
    return {
        "total_cases": total_cases,
        "single_and_comparison_cases": len(case_results),
        "pairwise_cases": len(pairwise_results),
        "fragmentation_detected_count": fragmentation_detected_count,
        "canonical_empty_cluster_populated_count": canonical_empty_cluster_populated_count,
        "entities_with_claims_canonical": entities_with_claims_canonical,
        "entities_with_claims_cluster": entities_with_claims_cluster,
        "total_canonical_claims": total_canonical_claims,
        "total_cluster_claims": total_cluster_claims,
        "total_pairwise_claims": total_pairwise_claims,
    }


def build_benchmark_case_result(
    *,
    case_def: BenchmarkCaseDefinition,
    canonical_rows: list[dict[str, Any]],
    cluster_rows: list[dict[str, Any]],
    lower_layer_rows: list[dict[str, Any]],
    fragmentation_check_rows: list[dict[str, Any]],
    catalog_check_rows: list[dict[str, Any]],
) -> BenchmarkCaseResult:
    canonical_claim_count = _count_distinct_claims(canonical_rows)
    cluster_claim_count = _count_distinct_claims(cluster_rows)
    canonical_cluster_count = _count_distinct_clusters(canonical_rows)
    cluster_name_cluster_count = _count_distinct(fragmentation_check_rows, "cluster_id")
    fragmentation = _detect_fragmentation(canonical_cluster_count, cluster_name_cluster_count)
    canonical_empty_cluster_populated = canonical_claim_count == 0 and cluster_claim_count > 0
    fragmentation_type_hints = _classify_fragmentation_type(
        fragmentation_check_rows,
        canonical_rows,
        cluster_rows,
        catalog_check_rows,
    )
    canonical_catalog_present = bool(catalog_check_rows)

    return BenchmarkCaseResult(
        case_id=case_def.case_id,
        case_type=case_def.case_type,
        entity_names=list(case_def.entity_names),
        description=case_def.description,
        expected_shape=case_def.expected_shape,
        failure_modes=list(case_def.failure_modes),
        canonical_rows=canonical_rows,
        cluster_rows=cluster_rows,
        lower_layer_rows=lower_layer_rows,
        fragmentation_check_rows=fragmentation_check_rows,
        canonical_claim_count=canonical_claim_count,
        cluster_claim_count=cluster_claim_count,
        canonical_cluster_count=canonical_cluster_count,
        cluster_name_cluster_count=cluster_name_cluster_count,
        fragmentation_detected=fragmentation,
        canonical_empty_cluster_populated=canonical_empty_cluster_populated,
        fragmentation_type_hints=fragmentation_type_hints,
        catalog_check_rows=catalog_check_rows,
        canonical_catalog_present=canonical_catalog_present,
    )


def build_benchmark_artifact(
    *,
    run_id: str | None,
    dataset_id: str | None = None,
    alignment_version: str | None,
    case_results: list[BenchmarkCaseResult],
    pairwise_results: list[PairwiseCaseResult],
    generated_at: str | None = None,
) -> RetrievalBenchmarkArtifact:
    timestamp = generated_at or datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    summary = _compute_benchmark_summary(case_results, pairwise_results)
    return RetrievalBenchmarkArtifact(
        generated_at=timestamp,
        run_id=run_id,
        dataset_id=dataset_id,
        alignment_version=alignment_version,
        case_results=[result.to_dict() for result in case_results],
        pairwise_results=[result.to_dict() for result in pairwise_results],
        benchmark_summary=summary,
    )


def run_retrieval_benchmark_runtime(
    *,
    dry_run: bool,
    output_dir: Path,
    neo4j_settings: Neo4jSettings | None,
    run_id: str | None = None,
    dataset_id: str | None = None,
    alignment_version: str | None = None,
    benchmark_cases: list[BenchmarkCaseDefinition] | None = None,
    suppress_alignment_version_warning: bool = False,
    logger: logging.Logger | None = None,
) -> dict[str, Any]:
    active_logger = _logger if logger is None else logger
    cases = benchmark_cases if benchmark_cases is not None else BENCHMARK_CASES
    effective_output_dir = Path(output_dir)
    runs_root = (effective_output_dir / "runs").resolve()

    if run_id == "":
        raise ValueError("run_id must be None or a non-empty string.")

    if dataset_id == "":
        raise ValueError("dataset_id must be None or a non-empty string.")

    if run_id is not None:
        run_id_path = Path(run_id)
        if run_id_path.is_absolute() or ".." in run_id_path.parts or run_id_path.name != run_id:
            raise ValueError(
                f"Invalid run_id {run_id!r}: must be a simple relative name without path separators or '..'."
            )
        run_root = (runs_root / run_id_path).resolve()
        if run_root == runs_root or runs_root not in run_root.parents:
            raise ValueError(
                f"Invalid run_id {run_id!r}: must resolve to a subdirectory of the runs directory."
            )
        artifact_dir = run_root / "retrieval_benchmark"
    else:
        artifact_dir = runs_root / "retrieval_benchmark"
    artifact_dir.mkdir(parents=True, exist_ok=True)
    artifact_path = artifact_dir / "retrieval_benchmark.json"

    collected_warnings: list[str] = []

    if run_id is None:
        collected_warnings.append(
            "run_retrieval_benchmark: run_id is None — benchmark will aggregate across ALL pipeline runs in the database, not just the current run. Pass run_id to scope queries to the intended pipeline execution."
        )

    if dataset_id is None:
        collected_warnings.append(
            "run_retrieval_benchmark: dataset_id is None — benchmark will aggregate across ALL datasets in the database, not just the current dataset. Results are not suitable for regression baselines in a multi-dataset graph. Pass dataset_id to scope queries to the intended dataset."
        )

    if alignment_version is None and not suppress_alignment_version_warning:
        collected_warnings.append(
            "run_retrieval_benchmark: alignment_version is None — benchmark will aggregate across ALL alignment versions in the database, not just the current cohort. Pass alignment_version (e.g. from the hybrid entity resolution stage output) to scope queries to the intended ALIGNED_WITH edge version."
        )

    if dry_run:
        dry_artifact_obj = build_benchmark_artifact(
            run_id=run_id,
            dataset_id=dataset_id,
            alignment_version=alignment_version,
            case_results=[],
            pairwise_results=[],
        )
        artifact_path.write_text(dry_artifact_obj.to_json(), encoding="utf-8")
        return {
            "status": "dry_run",
            "run_id": run_id,
            "dataset_id": dataset_id,
            "alignment_version": alignment_version,
            "artifact_path": str(artifact_path),
            "artifact": None,
            "warnings": ["retrieval benchmark skipped in dry_run mode"] + collected_warnings,
        }

    if neo4j_settings is None:
        raise ValueError("Retrieval benchmark requires Neo4j settings for live execution.")

    params: dict[str, Any] = {
        "run_id": run_id,
        "dataset_id": dataset_id,
        "alignment_version": alignment_version,
    }
    case_results: list[BenchmarkCaseResult] = []
    pairwise_results: list[PairwiseCaseResult] = []

    for case_def in cases:
        if not case_def.entity_names:
            raise ValueError(
                f"retrieval_benchmark: case {case_def.case_id!r} has empty entity_names"
            )
        entity_name = case_def.entity_names[0]

        if case_def.case_type == "pairwise_entity":
            if len(case_def.entity_names) < 2:
                active_logger.warning(
                    "retrieval_benchmark: pairwise case %r has fewer than 2 entity names; skipping",
                    case_def.case_id,
                )
                continue
            entity_a = case_def.entity_names[0]
            entity_b = case_def.entity_names[1]
            active_logger.info(
                "retrieval_benchmark: running pairwise case %r (%r <-> %r)",
                case_def.case_id,
                entity_a,
                entity_b,
            )
            query_rows = fetch_retrieval_benchmark_query_rows(
                neo4j_settings,
                neo4j_settings.database,
                base_params=params,
                query_specs=build_pairwise_query_specs(entity_a, entity_b),
                logger=active_logger,
            )
            pairwise_rows = query_rows["pairwise_rows"]
            pairwise_results.append(
                PairwiseCaseResult(
                    case_id=case_def.case_id,
                    entity_names=list(case_def.entity_names),
                    description=case_def.description,
                    expected_shape=case_def.expected_shape,
                    failure_modes=list(case_def.failure_modes),
                    pairwise_rows=pairwise_rows,
                    pairwise_claim_count=_count_distinct_claims(pairwise_rows),
                )
            )
        else:
            active_logger.info(
                "retrieval_benchmark: running case %r (entity=%r)",
                case_def.case_id,
                entity_name,
            )
            query_rows = fetch_retrieval_benchmark_query_rows(
                neo4j_settings,
                neo4j_settings.database,
                base_params=params,
                query_specs=build_single_entity_query_specs(entity_name),
                logger=active_logger,
            )
            case_results.append(
                build_benchmark_case_result(
                    case_def=case_def,
                    canonical_rows=query_rows["canonical_rows"],
                    cluster_rows=query_rows["cluster_rows"],
                    lower_layer_rows=query_rows["lower_layer_rows"],
                    fragmentation_check_rows=query_rows["fragmentation_check_rows"],
                    catalog_check_rows=query_rows["catalog_check_rows"],
                )
            )

    artifact = build_benchmark_artifact(
        run_id=run_id,
        dataset_id=dataset_id,
        alignment_version=alignment_version,
        case_results=case_results,
        pairwise_results=pairwise_results,
    )
    artifact_path.write_text(artifact.to_json(), encoding="utf-8")
    active_logger.info("retrieval_benchmark: artifact written to %s", artifact_path)

    return {
        "status": "live",
        "run_id": run_id,
        "dataset_id": dataset_id,
        "alignment_version": alignment_version,
        "artifact_path": str(artifact_path),
        "artifact": artifact.to_dict(),
        "warnings": collected_warnings,
    }


def run_retrieval_benchmark_runtime_default(**kwargs: Any) -> dict[str, Any]:
    return run_retrieval_benchmark_runtime(**kwargs)


__all__ = [
    "BENCHMARK_CASES",
    "BenchmarkCaseDefinition",
    "BenchmarkCaseResult",
    "PairwiseCaseResult",
    "RetrievalBenchmarkArtifact",
    "_Q_CANONICAL_SINGLE",
    "_Q_CATALOG_EXISTENCE_CHECK",
    "_Q_LOWER_LAYER_CHAIN",
    "_Q_PAIRWISE_CANONICAL",
    "_classify_fragmentation_type",
    "_compute_benchmark_summary",
    "_count_distinct",
    "_count_distinct_claims",
    "_count_distinct_clusters",
    "_detect_fragmentation",
    "_records_to_dicts",
    "build_benchmark_artifact",
    "build_benchmark_case_result",
    "run_retrieval_benchmark_runtime",
    "run_retrieval_benchmark_runtime_default",
]