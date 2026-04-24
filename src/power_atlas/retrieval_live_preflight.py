from __future__ import annotations

from typing import Any


def resolve_live_neo4j_settings(
    config: object,
    neo4j_settings: Any | None,
    *,
    neo4j_settings_type: type[Any],
    error_message: str,
) -> Any:
    """Resolve Neo4j settings for live retrieval from an explicit input or config."""
    if neo4j_settings is not None:
        return neo4j_settings
    config_settings = getattr(config, "settings", None)
    settings_neo4j = getattr(config_settings, "neo4j", None)
    if isinstance(settings_neo4j, neo4j_settings_type):
        return settings_neo4j
    raise ValueError(error_message)


def require_live_retrieval_openai_api_key(
    error_message: str,
    *,
    require_openai_api_key: Any,
    openai_api_key: str,
) -> None:
    """Require an OPENAI_API_KEY value before live retrieval setup."""
    require_openai_api_key(
        error_message,
        environ={"OPENAI_API_KEY": openai_api_key},
    )


def prepare_live_retrieval_preflight(
    config: object,
    neo4j_settings: Any | None,
    *,
    neo4j_settings_type: type[Any],
    require_openai_api_key: Any,
    openai_api_key: str,
    openai_error_message: str,
    neo4j_error_message: str,
) -> tuple[Any, str | None]:
    """Validate live retrieval prerequisites and return resolved Neo4j settings."""
    require_live_retrieval_openai_api_key(
        openai_error_message,
        require_openai_api_key=require_openai_api_key,
        openai_api_key=openai_api_key,
    )
    resolved_neo4j_settings = resolve_live_neo4j_settings(
        config,
        neo4j_settings,
        neo4j_settings_type=neo4j_settings_type,
        error_message=neo4j_error_message,
    )
    return resolved_neo4j_settings, resolved_neo4j_settings.database


__all__ = [
    "prepare_live_retrieval_preflight",
    "require_live_retrieval_openai_api_key",
    "resolve_live_neo4j_settings",
]