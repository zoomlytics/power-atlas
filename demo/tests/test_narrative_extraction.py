import json
import os
import sys
from pathlib import Path
from unittest import mock

import pytest
from neo4j_graphrag.experimental.components.types import (
    LexicalGraphConfig,
    Neo4jGraph,
    Neo4jNode,
    Neo4jRelationship,
    TextChunk,
    TextChunks,
)

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from demo.narrative_extraction import (  # noqa: E402
    PROMPT_VERSION,
    DEFAULT_NEO4J_PASSWORD,
    ExtractionConfig,
    build_lexical_config,
    prepare_extracted_rows,
    run_narrative_extraction,
)


def _build_fake_graph(chunk_id: str) -> Neo4jGraph:
    claim = Neo4jNode(
        id="claim-1",
        label="ExtractedClaim",
        properties={"claim_text": "A claim", "subject": "s", "predicate": "p", "object": "o", "confidence": 0.8},
    )
    mention = Neo4jNode(
        id="mention-1",
        label="EntityMention",
        properties={"name": "Example Entity", "entity_type": "ORG", "confidence": 0.6},
    )
    rel_claim = Neo4jRelationship(start_node_id=chunk_id, end_node_id=claim.id, type="MENTIONED_IN")
    rel_mention = Neo4jRelationship(start_node_id=chunk_id, end_node_id=mention.id, type="MENTIONED_IN")
    return Neo4jGraph(nodes=[claim, mention], relationships=[rel_claim, rel_mention])


def test_prepare_extracted_rows_builds_provenance_and_edges():
    lexical_config: LexicalGraphConfig = build_lexical_config()
    chunk_id = "chunk-1"
    text_chunks = [
        TextChunk(
            uid=chunk_id,
            text="chunk text",
            index=0,
            metadata={"page_number": 3, "run_id": "run-1", "source_uri": "uri://example"},
        )
    ]
    graph = _build_fake_graph(chunk_id)

    claim_rows, mention_rows, warnings = prepare_extracted_rows(
        graph=graph,
        text_chunks=text_chunks,
        run_id="run-1",
        source_uri="uri://example",
        lexical_graph_config=lexical_config,
    )

    assert warnings == []
    assert len(claim_rows) == 1
    assert len(mention_rows) == 1
    claim = claim_rows[0]
    mention = mention_rows[0]

    assert claim["chunk_ids"] == [chunk_id]
    assert mention["chunk_ids"] == [chunk_id]
    assert claim["properties"]["run_id"] == "run-1"
    assert claim["properties"]["page"] == 3
    # Process/stage metadata (prompt_version, extractor_model, extracted_at) must NOT
    # be written to graph node properties — they belong in manifests/artifacts only.
    assert "prompt_version" not in mention["properties"]
    assert "extractor_model" not in claim["properties"]
    assert "extracted_at" not in claim["properties"]
    assert "claims" not in mention["properties"]


def test_run_narrative_extraction_dry_run_writes_artifacts(tmp_path: Path):
    output_root = tmp_path / "runs"
    config = ExtractionConfig(
        run_id="run-123",
        source_uri=None,
        neo4j_uri="neo4j://localhost:7687",
        neo4j_username="neo4j",
        neo4j_password="testtesttest",
        neo4j_database="neo4j",
        model_name="gpt-4o-mini",
        output_root=output_root,
        dry_run=True,
    )

    summary = run_narrative_extraction(config)

    summary_path = output_root / config.run_id / "narrative_extraction" / "summary.json"
    manifest_path = output_root / config.run_id / "narrative_extraction" / "manifest.json"
    assert summary_path.exists()
    assert manifest_path.exists()

    stored_summary = json.loads(summary_path.read_text(encoding="utf-8"))
    stored_manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

    assert summary["status"] == "dry_run"
    assert stored_summary["prompt_version"] == PROMPT_VERSION
    assert stored_manifest["run_id"] == config.run_id
    assert stored_manifest["config"]["openai_model"] == config.model_name
    assert stored_manifest["stages"]["narrative_extraction"]["run_id"] == config.run_id
    assert stored_manifest["run_scopes"]["unstructured_ingest_run_id"] == config.run_id
    assert stored_manifest["run_scopes"]["batch_mode"] == "single_independent_run"


def test_run_narrative_extraction_live_path_uses_run_scoped_reader_and_writer(tmp_path: Path):
    lexical_config = build_lexical_config()
    fake_graph = _build_fake_graph("chunk-1")
    fake_chunks = TextChunks(
        chunks=[
            TextChunk(uid="chunk-1", text="chunk text", index=0, metadata={"page_number": 1, "run_id": "run-live"})
        ]
    )

    captured_calls = {"read": 0, "write_claims": 0, "write_mentions": 0}

    async def _fake_read_chunks_and_extract(driver, *, config, lexical_graph_config):
        captured_calls["read"] += 1
        assert config.run_id == "run-live"
        assert lexical_graph_config == lexical_config
        return fake_graph, fake_chunks.chunks

    def _fake_write_extracted_rows(
        driver,
        *,
        neo4j_database,
        lexical_graph_config,
        claim_rows,
        mention_rows,
    ):
        captured_calls["write_claims"] += len(claim_rows)
        captured_calls["write_mentions"] += len(mention_rows)
        assert neo4j_database == "neo4j"
        assert lexical_graph_config == lexical_config

    with mock.patch(
        "demo.narrative_extraction._read_chunks_and_extract",
        side_effect=_fake_read_chunks_and_extract,
    ), mock.patch(
            "demo.narrative_extraction.write_extracted_rows",
            side_effect=_fake_write_extracted_rows,
        ), mock.patch("neo4j.GraphDatabase.driver"):
        config = ExtractionConfig(
            run_id="run-live",
            source_uri="file:///doc.pdf",
            neo4j_uri="neo4j://localhost:7687",
            neo4j_username="neo4j",
            neo4j_password="testtesttest",
            neo4j_database="neo4j",
            model_name="gpt-4o-mini",
            output_root=tmp_path,
            dry_run=False,
        )
        with mock.patch.dict(os.environ, {"OPENAI_API_KEY": "test-key"}):
            summary = run_narrative_extraction(config)

    assert captured_calls["read"] == 1
    assert captured_calls["write_claims"] == 1
    assert captured_calls["write_mentions"] == 1
    assert summary["status"] == "live"
    assert summary["claims"] == 1
    assert summary["mentions"] == 1


def test_run_narrative_extraction_rejects_default_password_for_live(tmp_path: Path):
    config = ExtractionConfig(
        run_id="run-live",
        source_uri=None,
        neo4j_uri="neo4j://localhost:7687",
        neo4j_username="neo4j",
        neo4j_password=DEFAULT_NEO4J_PASSWORD,
        neo4j_database="neo4j",
        model_name="gpt-4o-mini",
        output_root=tmp_path,
        dry_run=False,
    )

    with pytest.raises(ValueError, match="NEO4J_PASSWORD must be set"):
        run_narrative_extraction(config)


def test_write_extracted_rows_validates_cypher_identifiers():
    from demo import narrative_extraction  # import inside to use updated helper

    class _FakeDriver:
        def execute_query(self, *args, **kwargs):
            raise AssertionError("execute_query should not be called when identifiers are invalid")

    bad_config = LexicalGraphConfig(chunk_node_label="Chunk:Bad", chunk_id_property="chunk_id")

    with pytest.raises(ValueError, match="Unsafe chunk label"):
        narrative_extraction.write_extracted_rows(
            _FakeDriver(),
            neo4j_database="neo4j",
            lexical_graph_config=bad_config,
            claim_rows=[],
            mention_rows=[],
        )


def test_write_extracted_rows_validates_chunk_id_property():
    from demo import narrative_extraction  # import inside to use updated helper

    class _FakeDriver:
        def execute_query(self, *args, **kwargs):
            raise AssertionError("execute_query should not be called when identifiers are invalid")

    bad_config = LexicalGraphConfig(chunk_node_label="Chunk", chunk_id_property="chunk-id")

    with pytest.raises(ValueError, match="Unsafe chunk_id property"):
        narrative_extraction.write_extracted_rows(
            _FakeDriver(),
            neo4j_database="neo4j",
            lexical_graph_config=bad_config,
            claim_rows=[],
            mention_rows=[],
        )


def test_write_extracted_rows_allows_valid_identifiers_and_executes():
    from demo import narrative_extraction  # import inside to use updated helper

    executed = {"count": 0}

    class _FakeDriver:
        def execute_query(self, *args, **kwargs):
            executed["count"] += 1
            return None

    good_config = LexicalGraphConfig(chunk_node_label="Chunk", chunk_id_property="chunk_id")
    claim_rows = [
        {
            "claim_id": "claim-1",
            "chunk_ids": ["chunk-1"],
            "run_id": "run-valid",
            "source_uri": None,
            "properties": {"run_id": "run-valid", "claim_text": "A claim"},
        }
    ]

    narrative_extraction.write_extracted_rows(
        _FakeDriver(),
        neo4j_database="neo4j",
        lexical_graph_config=good_config,
        claim_rows=claim_rows,
        mention_rows=[],
    )

    assert executed["count"] == 1
