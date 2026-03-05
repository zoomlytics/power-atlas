import asyncio
import importlib.util
import sys
from pathlib import Path

import pytest
from neo4j_graphrag.experimental.components.types import LexicalGraphConfig

MODULE_PATH = Path(__file__).resolve().parents[1] / "demo" / "chain_of_custody" / "io" / "run_scoped_chunk_reader.py"


def _load_reader():
    spec = importlib.util.spec_from_file_location("run_scoped_chunk_reader_test", MODULE_PATH)
    if spec is None or spec.loader is None:
        raise ImportError(f"Cannot import {MODULE_PATH}")
    module = importlib.util.module_from_spec(spec)
    try:
        sys.modules["run_scoped_chunk_reader_test"] = module
        spec.loader.exec_module(module)
    finally:
        sys.modules.pop("run_scoped_chunk_reader_test", None)
    return module.RunScopedNeo4jChunkReader


class _FakeDriver:
    def __init__(self, records):
        self._records = records
        self.calls: list[tuple[str, dict | None, dict]] = []
        pool_config = type("PoolConfig", (), {"user_agent": None})
        self._pool = type("Pool", (), {"pool_config": pool_config()})()

    def execute_query(self, query, parameters_=None, **kwargs):
        self.calls.append((query, parameters_, kwargs))
        return self._records, None, None


def _run_reader(records, **reader_kwargs):
    driver = _FakeDriver(records)
    reader_cls = _load_reader()
    reader = reader_cls(driver, run_id="run-123", source_uri="source-abc", **reader_kwargs)
    config = LexicalGraphConfig(
        chunk_id_property="chunk_id",
        chunk_index_property="chunk_index",
        chunk_text_property="text",
    )
    chunks = asyncio.run(reader.run(config))
    return driver, chunks


def test_run_scoped_reader_filters_and_orders_results():
    driver, chunks = _run_reader(
        [{"chunk": {"text": "hello", "chunk_index": 1, "chunk_id": "c1", "run_id": "run-123", "source_uri": "source-abc"}}]
    )
    assert len(chunks.chunks) == 1
    query, params, _ = driver.calls[0]
    assert "WHERE c.run_id = $run_id" in query
    assert "c.source_uri = $source_uri" in query
    assert "ORDER BY c.chunk_index" in query
    assert params == {"run_id": "run-123", "source_uri": "source-abc"}


def test_run_scoped_reader_raises_when_no_chunks_returned():
    reader_cls = _load_reader()
    reader = reader_cls(_FakeDriver([]), run_id="missing-run")
    config = LexicalGraphConfig(
        chunk_id_property="chunk_id",
        chunk_index_property="chunk_index",
        chunk_text_property="text",
    )
    with pytest.raises(ValueError):
        asyncio.run(reader.run(config))
