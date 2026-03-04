from __future__ import annotations

import importlib.util
from pathlib import Path
from typing import Type


def load_run_scoped_reader() -> Type:
    """Dynamically load the RunScopedNeo4jChunkReader from this package."""
    components_root = Path(__file__).resolve().parents[1]
    chunk_reader_path = components_root / "chunk_reader" / "neo4j_chunk_reader.py"
    if not chunk_reader_path.exists():
        raise RuntimeError(f"Chunk reader module not found at {chunk_reader_path}")
    spec = importlib.util.spec_from_file_location("run_scoped_chunk_reader", chunk_reader_path)
    if spec is None or spec.loader is None:
        raise ImportError(f"Unable to load chunk reader module from {chunk_reader_path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.RunScopedNeo4jChunkReader
