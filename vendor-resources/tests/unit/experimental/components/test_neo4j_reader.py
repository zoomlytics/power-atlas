#  Copyright (c) "Neo4j"
#  Neo4j Sweden AB [https://neo4j.com]
#  #
#  Licensed under the Apache License, Version 2.0 (the "License");
#  you may not use this file except in compliance with the License.
#  You may obtain a copy of the License at
#  #
#      https://www.apache.org/licenses/LICENSE-2.0
#  #
#  Unless required by applicable law or agreed to in writing, software
#  distributed under the License is distributed on an "AS IS" BASIS,
#  WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
#  See the License for the specific language governing permissions and
#  limitations under the License.
from unittest.mock import Mock

import neo4j
import pytest
import importlib.util
from pathlib import Path
from neo4j_graphrag.experimental.components.neo4j_reader import (
    Neo4jChunkReader,
)
from neo4j_graphrag.experimental.components.types import LexicalGraphConfig, TextChunks


def _load_run_scoped_reader_class():
    test_path = Path(__file__).resolve()
    examples_root = None
    for parent in test_path.parents:
        if parent.name == "vendor-resources":
            candidate = parent / "examples"
            if candidate.exists():
                examples_root = candidate
                break
    if examples_root is None:
        raise RuntimeError("Unable to locate vendor-resources/examples directory")
    utils_path = (
        examples_root
        / "customize"
        / "build_graph"
        / "components"
        / "chunk_reader"
        / "utils.py"
    )
    if not utils_path.exists():
        raise RuntimeError(f"Expected chunk reader utilities at {utils_path} were not found")
    spec = importlib.util.spec_from_file_location("chunk_reader_utils", utils_path)
    if spec is None or spec.loader is None:
        raise ImportError(f"Unable to load chunk reader utilities from {utils_path}")
    utils_module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(utils_module)
    return utils_module.load_run_scoped_reader()


@pytest.fixture(scope="module")
def run_scoped_reader_cls():
    return _load_run_scoped_reader_class()


@pytest.mark.asyncio
async def test_neo4j_chunk_reader(driver: Mock) -> None:
    driver.execute_query.return_value = (
        [neo4j.Record({"chunk": {"index": 0, "text": "some text", "id": "azerty"}})],
        None,
        None,
    )
    chunk_reader = Neo4jChunkReader(driver, neo4j_database="mydb")
    res = await chunk_reader.run()

    driver.execute_query.assert_called_once_with(
        "MATCH (c:`Chunk`) RETURN c { .*, embedding: null } as chunk ORDER BY c.index",
        database_="mydb",
        routing_=neo4j.RoutingControl.READ,
    )

    assert isinstance(res, TextChunks)
    assert len(res.chunks) == 1
    chunk = res.chunks[0]
    assert chunk.uid == "azerty"
    assert chunk.text == "some text"
    assert chunk.index == 0
    assert chunk.metadata == {}


@pytest.mark.asyncio
async def test_neo4j_chunk_reader_custom_lg_config(driver: Mock) -> None:
    driver.execute_query.return_value = (
        [
            neo4j.Record(
                {
                    "chunk": {
                        "k": 0,
                        "content": "some text",
                        "id": "azerty",
                        "other": "property",
                    }
                }
            )
        ],
        None,
        None,
    )
    chunk_reader = Neo4jChunkReader(driver)
    res = await chunk_reader.run(
        lexical_graph_config=LexicalGraphConfig(
            chunk_node_label="Page",
            chunk_text_property="content",
            chunk_index_property="k",
        )
    )

    driver.execute_query.assert_called_once_with(
        "MATCH (c:`Page`) RETURN c { .*, embedding: null } as chunk ORDER BY c.k",
        database_=None,
        routing_=neo4j.RoutingControl.READ,
    )

    assert isinstance(res, TextChunks)
    assert len(res.chunks) == 1
    chunk = res.chunks[0]
    assert chunk.uid == "azerty"
    assert chunk.text == "some text"
    assert chunk.index == 0
    assert chunk.metadata == {"other": "property"}


@pytest.mark.asyncio
async def test_neo4j_chunk_reader_fetch_embedding(driver: Mock) -> None:
    driver.execute_query.return_value = (
        [
            neo4j.Record(
                {
                    "chunk": {
                        "index": 0,
                        "text": "some text",
                        "other": "property",
                        "embedding": [1.0, 2.0, 3.0],
                        "id": "azerty",
                    }
                }
            )
        ],
        None,
        None,
    )
    chunk_reader = Neo4jChunkReader(driver, fetch_embeddings=True)
    res = await chunk_reader.run()

    driver.execute_query.assert_called_once_with(
        "MATCH (c:`Chunk`) RETURN c { .* } as chunk ORDER BY c.index",
        database_=None,
        routing_=neo4j.RoutingControl.READ,
    )

    assert isinstance(res, TextChunks)
    assert len(res.chunks) == 1
    chunk = res.chunks[0]
    assert chunk.uid == "azerty"
    assert chunk.text == "some text"
    assert chunk.index == 0
    assert chunk.metadata == {
        "other": "property",
        "embedding": [1.0, 2.0, 3.0],
    }


@pytest.mark.asyncio
async def test_run_scoped_chunk_reader_filters(
    driver: Mock, run_scoped_reader_cls
) -> None:
    driver.execute_query.return_value = (
        [
            neo4j.Record(
                {
                    "chunk": {
                        "index": 1,
                        "text": "filtered text",
                        "id": "chunk-1",
                        "run_id": "run-123",
                        "source_uri": "file://source.pdf",
                    }
                }
            )
        ],
        None,
        None,
    )
    chunk_reader = run_scoped_reader_cls(
        driver,
        run_id="run-123",
        source_uri="file://source.pdf",
    )
    res = await chunk_reader.run()

    driver.execute_query.assert_called_once_with(
        "MATCH (c:`Chunk`)\n"
        "WHERE c.run_id = $run_id AND c.source_uri = $source_uri\n"
        "RETURN c { .*, embedding: null } as chunk ORDER BY c.index",
        database_=None,
        routing_=neo4j.RoutingControl.READ,
        run_id="run-123",
        source_uri="file://source.pdf",
    )
    assert isinstance(res, TextChunks)
    assert len(res.chunks) == 1
    assert res.chunks[0].uid == "chunk-1"
    assert res.chunks[0].index == 1


@pytest.mark.asyncio
async def test_run_scoped_chunk_reader_empty(driver: Mock, run_scoped_reader_cls) -> None:
    driver.execute_query.return_value = ([], None, None)
    chunk_reader = run_scoped_reader_cls(driver, run_id="missing-run")

    with pytest.raises(ValueError, match="missing-run"):
        await chunk_reader.run()
