from __future__ import annotations

from dataclasses import replace
from typing import Any, Callable

from power_atlas.context import RequestContext
from power_atlas.settings import Neo4jSettings


def coerce_run_scope_query_neo4j_settings(
    config: Any,
    *,
    resolve_neo4j_settings: Callable[[Any], Neo4jSettings],
) -> Neo4jSettings:
    try:
        return resolve_neo4j_settings(config)
    except ValueError:
        uri = getattr(config, "neo4j_uri", None)
        username = getattr(config, "neo4j_username", None)
        password = getattr(config, "neo4j_password", None)
        database = getattr(config, "neo4j_database", None)
        if all(isinstance(value, str) and value for value in (uri, username, password)):
            return Neo4jSettings(
                uri=uri,
                username=username,
                password=password,
                database=database,
            )
        raise


def prepare_ask_request_context_from_scope(
    request_context: RequestContext,
    *,
    resolved_run_id: str | None,
    all_runs: bool,
    resolve_ask_source_uri: Callable[[RequestContext], str | None],
) -> RequestContext:
    prepared_request_context = request_context
    if resolved_run_id != request_context.run_id or all_runs != request_context.all_runs:
        prepared_request_context = replace(
            request_context,
            run_id=resolved_run_id,
            all_runs=all_runs,
        )
    return replace(
        prepared_request_context,
        source_uri=resolve_ask_source_uri(prepared_request_context),
    )


__all__ = [
    "coerce_run_scope_query_neo4j_settings",
    "prepare_ask_request_context_from_scope",
]