from __future__ import annotations

from importlib import import_module
from typing import Any

__all__ = ["ProvenanceNeo4jWriter", "RunScopedNeo4jChunkReader"]

_LAZY_IMPORTS = {
    "ProvenanceNeo4jWriter": ("demo.io.provenance_writer", "ProvenanceNeo4jWriter"),
    "RunScopedNeo4jChunkReader": ("demo.io.run_scoped_chunk_reader", "RunScopedNeo4jChunkReader"),
}


def __getattr__(name: str) -> Any:  # pragma: no cover - import proxy
    if name in _LAZY_IMPORTS:
        module_name, attr_name = _LAZY_IMPORTS[name]
        module = import_module(module_name)
        value = getattr(module, attr_name)
        globals()[name] = value
        return value
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


def __dir__() -> list[str]:  # pragma: no cover - import proxy
    return sorted(__all__)
