from __future__ import annotations

from importlib import import_module
from typing import Any


_BACKEND_APP_EXPORTS = (
	"BackendAppOptions",
	"BackendRuntime",
	"backend_router",
	"build_backend_runtime",
	"build_backend_router",
	"create_backend_app",
	"get_backend_runtime",
	"lifespan",
)

_BACKEND_GRAPH_EXPORTS = (
	"BackendGraphQueryService",
	"build_backend_graph_query_service",
)

_BACKEND_GRAPH_API_MODEL_EXPORTS = (
)

_EXPORT_MODULES = {
	**{name: ("power_atlas.backend_app", name) for name in _BACKEND_APP_EXPORTS},
	**{name: ("power_atlas.backend_graph", name) for name in _BACKEND_GRAPH_EXPORTS},
	**{
		name: ("power_atlas.backend_graph_api_models", name)
		for name in _BACKEND_GRAPH_API_MODEL_EXPORTS
	},
}


__all__ = [
	"BackendAppOptions",
	"BackendRuntime",
	"backend_router",
	"build_backend_runtime",
	"build_backend_router",
	"create_backend_app",
	"get_backend_runtime",
	"lifespan",
	"BackendGraphQueryService",
	"build_backend_graph_query_service",
]


def __getattr__(name: str) -> Any:
	try:
		module_name, attribute_name = _EXPORT_MODULES[name]
	except KeyError as exc:
		raise AttributeError(f"module {__name__!r} has no attribute {name!r}") from exc
	value = getattr(import_module(module_name), attribute_name)
	globals()[name] = value
	return value


def __dir__() -> list[str]:
	return sorted(set(globals()) | set(__all__))