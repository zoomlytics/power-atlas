from __future__ import annotations

from dataclasses import replace
import logging
from typing import Callable

from power_atlas.context import RequestContext


def format_dataset_label(
    config_dataset: str | None,
    power_atlas_dataset: str | None,
    fixture_dataset: str | None,
) -> str:
    if config_dataset and power_atlas_dataset and config_dataset != power_atlas_dataset:
        return (
            f"--dataset={config_dataset!r} "
            f"(overrides POWER_ATLAS_DATASET={power_atlas_dataset!r})"
        )
    if config_dataset and fixture_dataset and config_dataset != fixture_dataset:
        return (
            f"--dataset={config_dataset!r} "
            f"(overrides FIXTURE_DATASET={fixture_dataset!r})"
        )
    if power_atlas_dataset and fixture_dataset and power_atlas_dataset != fixture_dataset:
        return (
            f"POWER_ATLAS_DATASET={power_atlas_dataset!r} "
            f"(overrides FIXTURE_DATASET={fixture_dataset!r})"
        )
    if power_atlas_dataset:
        return f"POWER_ATLAS_DATASET={power_atlas_dataset!r}"
    if fixture_dataset:
        return f"FIXTURE_DATASET={fixture_dataset!r}"
    return f"--dataset={config_dataset!r}"


def warn_explicit_run_id_dataset_mismatch(
    explicit_run_id: str,
    expected_dataset_id: str,
    actual_dataset_id: str,
    *,
    config_dataset: str | None,
    power_atlas_dataset: str | None,
    fixture_dataset: str | None,
    logger: logging.Logger,
) -> None:
    dataset_label = format_dataset_label(config_dataset, power_atlas_dataset, fixture_dataset)
    logger.warning(
        "--run-id=%r belongs to dataset %r, "
        "but %s is selected (expected dataset_id=%r). "
        "Retrieval will be scoped to a run from a different dataset than requested. "
        "Use --latest to select the latest run for the selected dataset instead.",
        explicit_run_id,
        actual_dataset_id,
        dataset_label,
        expected_dataset_id,
    )


def warn_env_run_id_dataset_mismatch(
    env_run_id: str,
    config_dataset: str | None,
    power_atlas_dataset: str | None,
    fixture_dataset: str | None,
    *,
    logger: logging.Logger,
) -> None:
    dataset_label = format_dataset_label(config_dataset, power_atlas_dataset, fixture_dataset)
    logger.warning(
        "UNSTRUCTURED_RUN_ID=%r is set and will be "
        "used as the retrieval scope, but %s "
        "is also selected. UNSTRUCTURED_RUN_ID bypasses dataset-aware run "
        "selection and may retrieve from a run that belongs to a different "
        "dataset. Use --latest (in --live mode) to resolve the latest run "
        "for the selected dataset, or --run-id to target a specific run explicitly.",
        env_run_id,
        dataset_label,
    )


def warn_if_env_run_id_bypasses_dataset_selection(
    env_run_id: str,
    *,
    config_dataset: str | None,
    current_env_dataset_selection: Callable[[], tuple[str | None, str | None, str | None]],
    logger: logging.Logger,
) -> None:
    power_atlas_dataset, fixture_dataset, effective_env_dataset = current_env_dataset_selection()
    if config_dataset or effective_env_dataset:
        warn_env_run_id_dataset_mismatch(
            env_run_id,
            config_dataset,
            power_atlas_dataset,
            fixture_dataset,
            logger=logger,
        )


def validate_explicit_run_id_dataset_selection(
    config,
    explicit_run_id: str,
    *,
    current_env_dataset_selection: Callable[[], tuple[str | None, str | None, str | None]],
    resolve_dataset_root: Callable[[str], object],
    fetch_dataset_id_for_run: Callable[[object, str], str | None],
    logger: logging.Logger,
) -> None:
    if config.dry_run:
        return

    config_dataset = config.dataset_name
    power_atlas_dataset, fixture_dataset, effective_env_dataset = current_env_dataset_selection()
    effective_dataset = config_dataset or effective_env_dataset
    if not effective_dataset:
        return

    try:
        expected_dataset_id = resolve_dataset_root(effective_dataset).dataset_id
    except ValueError as exc:
        logger.warning(
            "Could not resolve dataset %r to "
            "validate --run-id dataset ownership "
            "(%s). Dataset-ownership check skipped.",
            effective_dataset,
            exc,
        )
        return

    actual_dataset_id = fetch_dataset_id_for_run(config, explicit_run_id)
    if actual_dataset_id is not None and actual_dataset_id != expected_dataset_id:
        warn_explicit_run_id_dataset_mismatch(
            explicit_run_id,
            expected_dataset_id,
            actual_dataset_id,
            config_dataset=config_dataset,
            power_atlas_dataset=power_atlas_dataset,
            fixture_dataset=fixture_dataset,
            logger=logger,
        )


def resolve_latest_dataset_id(
    config,
    *,
    current_env_dataset_selection: Callable[[], tuple[str | None, str | None, str | None]],
    resolve_dataset_root: Callable[[str], object],
) -> str | None:
    try:
        return resolve_dataset_root(config.dataset_name).dataset_id
    except ValueError as exc:
        _power_atlas_dataset, _fixture_dataset, explicit_env_dataset = current_env_dataset_selection()
        explicit_source = config.dataset_name or explicit_env_dataset
        if explicit_source:
            raise SystemExit(f"Failed to resolve dataset {explicit_source!r}: {exc}") from exc
        return None


def resolve_latest_run_scope(
    config,
    *,
    env_run_id: str | None,
    use_latest: bool,
    current_env_dataset_selection: Callable[[], tuple[str | None, str | None, str | None]],
    resolve_dataset_root: Callable[[str], object],
    fetch_latest_unstructured_run_id: Callable[[object, str | None], str | None],
    logger: logging.Logger,
) -> str:
    resolved_dataset_id = resolve_latest_dataset_id(
        config,
        current_env_dataset_selection=current_env_dataset_selection,
        resolve_dataset_root=resolve_dataset_root,
    )
    latest_run_id = fetch_latest_unstructured_run_id(config, resolved_dataset_id)
    if latest_run_id is None:
        raise SystemExit(
            "No unstructured ingest runs found in the database. "
            "Run 'ingest-pdf' first, or use --all-runs to query all available data."
        )
    if use_latest and env_run_id and env_run_id != latest_run_id:
        logger.warning(
            "UNSTRUCTURED_RUN_ID=%r is set but overridden by --latest. "
            "Using latest: %r.",
            env_run_id,
            latest_run_id,
        )
    return latest_run_id


def resolve_dry_run_ask_scope(
    config,
    *,
    env_run_id: str | None,
    current_env_dataset_selection: Callable[[], tuple[str | None, str | None, str | None]],
    logger: logging.Logger,
) -> tuple[str | None, bool]:
    if env_run_id:
        warn_if_env_run_id_bypasses_dataset_selection(
            env_run_id,
            config_dataset=config.dataset_name,
            current_env_dataset_selection=current_env_dataset_selection,
            logger=logger,
        )
        return env_run_id, False
    return None, False


def resolve_ask_request_context(
    args,
    request_context: RequestContext,
    *,
    current_env_unstructured_run_id: Callable[[], str | None],
    current_env_dataset_selection: Callable[[], tuple[str | None, str | None, str | None]],
    fetch_dataset_id_for_run: Callable[[object, str], str | None],
    fetch_latest_unstructured_run_id: Callable[[object, str | None], str | None],
    resolve_dataset_root: Callable[[str], object],
    logger: logging.Logger,
) -> RequestContext:
    config = request_context.config
    env_run_id = current_env_unstructured_run_id()
    all_runs: bool = getattr(args, "all_runs", False)
    explicit_run_id: str | None = getattr(args, "run_id", None)
    use_latest: bool = getattr(args, "latest", False)

    if all_runs:
        if env_run_id:
            logger.warning(
                "UNSTRUCTURED_RUN_ID=%r is set "
                "but overridden by --all-runs.",
                env_run_id,
            )
        return replace(request_context, run_id=None, all_runs=True)

    if explicit_run_id:
        if env_run_id and env_run_id != explicit_run_id:
            logger.warning(
                "UNSTRUCTURED_RUN_ID=%r is set "
                "but overridden by --run-id=%r.",
                env_run_id,
                explicit_run_id,
            )
        validate_explicit_run_id_dataset_selection(
            config,
            explicit_run_id,
            current_env_dataset_selection=current_env_dataset_selection,
            resolve_dataset_root=resolve_dataset_root,
            fetch_dataset_id_for_run=fetch_dataset_id_for_run,
            logger=logger,
        )
        return replace(request_context, run_id=explicit_run_id, all_runs=False)

    if config.dry_run:
        resolved_run_id, resolved_all_runs = resolve_dry_run_ask_scope(
            config,
            env_run_id=env_run_id,
            current_env_dataset_selection=current_env_dataset_selection,
            logger=logger,
        )
        return replace(request_context, run_id=resolved_run_id, all_runs=resolved_all_runs)

    if not use_latest and env_run_id:
        warn_if_env_run_id_bypasses_dataset_selection(
            env_run_id,
            config_dataset=config.dataset_name,
            current_env_dataset_selection=current_env_dataset_selection,
            logger=logger,
        )
        return replace(request_context, run_id=env_run_id, all_runs=False)

    return replace(
        request_context,
        run_id=resolve_latest_run_scope(
            config,
            env_run_id=env_run_id,
            use_latest=use_latest,
            current_env_dataset_selection=current_env_dataset_selection,
            resolve_dataset_root=resolve_dataset_root,
            fetch_latest_unstructured_run_id=fetch_latest_unstructured_run_id,
            logger=logger,
        ),
        all_runs=False,
    )


def resolve_ask_scope(
    args,
    request_context_or_config,
    *,
    ensure_request_context: Callable[..., RequestContext],
    current_env_unstructured_run_id: Callable[[], str | None],
    current_env_dataset_selection: Callable[[], tuple[str | None, str | None, str | None]],
    fetch_dataset_id_for_run: Callable[[object, str], str | None],
    fetch_latest_unstructured_run_id: Callable[[object, str | None], str | None],
    resolve_dataset_root: Callable[[str], object],
    logger: logging.Logger,
) -> tuple[str | None, bool]:
    request_context = ensure_request_context(request_context_or_config, command="ask")
    resolved_request_context = resolve_ask_request_context(
        args,
        request_context,
        current_env_unstructured_run_id=current_env_unstructured_run_id,
        current_env_dataset_selection=current_env_dataset_selection,
        fetch_dataset_id_for_run=fetch_dataset_id_for_run,
        fetch_latest_unstructured_run_id=fetch_latest_unstructured_run_id,
        resolve_dataset_root=resolve_dataset_root,
        logger=logger,
    )
    return resolved_request_context.run_id, resolved_request_context.all_runs


def resolve_ask_source_uri(
    request_context: RequestContext,
    *,
    resolve_dataset_root: Callable[[str], object],
) -> str | None:
    if request_context.all_runs:
        return None
    return str(resolve_dataset_root(request_context.config.dataset_name).pdf_path.resolve().as_uri())


def prepare_ask_request_context(
    args,
    request_context_or_config,
    *,
    ensure_request_context: Callable[..., RequestContext],
    current_env_unstructured_run_id: Callable[[], str | None],
    current_env_dataset_selection: Callable[[], tuple[str | None, str | None, str | None]],
    fetch_dataset_id_for_run: Callable[[object, str], str | None],
    fetch_latest_unstructured_run_id: Callable[[object, str | None], str | None],
    resolve_dataset_root: Callable[[str], object],
    logger: logging.Logger,
) -> RequestContext:
    request_context = ensure_request_context(request_context_or_config, command="ask")
    request_context = resolve_ask_request_context(
        args,
        request_context,
        current_env_unstructured_run_id=current_env_unstructured_run_id,
        current_env_dataset_selection=current_env_dataset_selection,
        fetch_dataset_id_for_run=fetch_dataset_id_for_run,
        fetch_latest_unstructured_run_id=fetch_latest_unstructured_run_id,
        resolve_dataset_root=resolve_dataset_root,
        logger=logger,
    )
    return replace(
        request_context,
        source_uri=resolve_ask_source_uri(
            request_context,
            resolve_dataset_root=resolve_dataset_root,
        ),
    )


__all__ = [
    "format_dataset_label",
    "prepare_ask_request_context",
    "resolve_ask_request_context",
    "resolve_ask_scope",
    "resolve_ask_source_uri",
    "resolve_dry_run_ask_scope",
    "resolve_latest_dataset_id",
    "resolve_latest_run_scope",
    "validate_explicit_run_id_dataset_selection",
    "warn_env_run_id_dataset_mismatch",
    "warn_explicit_run_id_dataset_mismatch",
    "warn_if_env_run_id_bypasses_dataset_selection",
]