from __future__ import annotations

import csv
import json
import os
from pathlib import Path
from unittest import mock

import pytest
from neo4j_graphrag.experimental.components.types import (
    Neo4jGraph,
    Neo4jNode,
    Neo4jRelationship,
    TextChunk,
    TextChunks,
)

from demo.contracts.manifest import build_batch_manifest, build_stage_manifest
from demo.contracts.pipeline import (
    CHUNK_EMBEDDING_DIMENSIONS,
    CHUNK_EMBEDDING_INDEX_NAME,
    CHUNK_EMBEDDING_LABEL,
    CHUNK_EMBEDDING_PROPERTY,
)
from demo.contracts.prompts import PROMPT_IDS
from demo.contracts.runtime import Config, make_run_id
from demo.contracts.structured import STRUCTURED_FILE_HEADERS
from demo.stages import lint_and_clean_structured_csvs, run_pdf_ingest


def _dry_run_config(tmp_path: Path) -> Config:
    return Config(
        dry_run=True,
        output_dir=tmp_path,
        neo4j_uri="bolt://example.invalid",
        neo4j_username="neo4j",
        neo4j_password="not-used",
        neo4j_database="neo4j",
        openai_model="test-model",
    )


def test_make_run_id_uses_scope_prefix():
    run_id = make_run_id("example")
    assert run_id.startswith("example-")


def test_batch_manifest_includes_stage_runs(tmp_path: Path):
    manifest = build_batch_manifest(
        config=_dry_run_config(tmp_path),
        structured_run_id="structured-1",
        unstructured_run_id="unstructured-2",
        resolution_run_id="resolution-3",
        structured_stage={"status": "dry_run"},
        pdf_stage={"status": "dry_run"},
        claim_stage={"status": "dry_run"},
        retrieval_stage={"status": "dry_run"},
    )
    assert manifest["stages"]["structured_ingest"]["run_id"] == "structured-1"
    assert manifest["stages"]["pdf_ingest"]["run_id"] == "unstructured-2"
    assert manifest["stages"]["claim_and_mention_extraction"]["run_id"] == "unstructured-2"
    assert manifest["stages"]["retrieval_and_qa"]["run_id"] == "unstructured-2"


def test_stage_manifest_carries_config(tmp_path: Path):
    config = _dry_run_config(tmp_path)
    manifest = build_stage_manifest(
        config=config,
        stage_name="pdf_ingest",
        stage_run_id="stage-123",
        run_scope_key="unstructured_ingest_run_id",
        stage_output={"status": "dry_run"},
    )
    assert manifest["run_scopes"]["unstructured_ingest_run_id"] == "stage-123"
    assert manifest["config"]["dry_run"] is True


def test_structured_lint_writes_clean_files(tmp_path: Path):
    result = lint_and_clean_structured_csvs(run_id="test-run", output_dir=tmp_path)
    clean_dir = Path(result["structured_clean_dir"])
    assert clean_dir.exists()
    assert Path(result["lint_report_path"]).exists()
    assert result["lint_summary"]["status"] == "ok"


def _write_structured_csv(structured_dir: Path, name: str, headers: list[str], rows: list[dict[str, str]]) -> None:
    structured_dir.mkdir(parents=True, exist_ok=True)
    with (structured_dir / name).open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=headers)
        writer.writeheader()
        writer.writerows(rows)


def test_structured_lint_reports_and_raises_on_invalid_data(tmp_path: Path):
    fixtures_dir = tmp_path / "fixtures"
    structured_dir = fixtures_dir / "structured"

    _write_structured_csv(
        structured_dir,
        "entities.csv",
        headers=STRUCTURED_FILE_HEADERS["entities.csv"] + ["extra"],
        rows=[
            {
                "entity_id": "Q1",
                "name": "Example Entity",
                "entity_type": "person",
                "aliases": "",
                "description": "",
                "wikidata_url": "https://example.invalid/entity/Q1",
                "extra": "ignored",
            }
        ],
    )
    _write_structured_csv(
        structured_dir,
        "facts.csv",
        headers=STRUCTURED_FILE_HEADERS["facts.csv"],
        rows=[
            {
                "fact_id": "F1",
                "subject_id": "Q1",
                "subject_label": "Example Entity",
                "predicate_pid": "P22",
                "predicate_label": "father",
                "value": "Someone",
                "value_type": "string",
                "source": "example",
                "source_url": "https://example.invalid/f1",
                "retrieved_at": "2020-01-01",
            }
        ],
    )
    _write_structured_csv(
        structured_dir,
        "relationships.csv",
        headers=STRUCTURED_FILE_HEADERS["relationships.csv"],
        rows=[],
    )
    _write_structured_csv(
        structured_dir,
        "claims.csv",
        headers=STRUCTURED_FILE_HEADERS["claims.csv"],
        rows=[
            {
                "claim_id": "C1",
                "claim_type": "fact",
                "subject_id": "Q2",
                "subject_label": "Unknown Subject",
                "predicate_pid": "P22",
                "predicate_label": "father",
                "object_id": "",
                "object_label": "",
                "value": "Someone",
                "value_type": "string",
                "claim_text": "Claim text",
                "confidence": "0.5",
                "source": "example",
                "source_url": "https://example.invalid/c1",
                "retrieved_at": "2020-01-01",
                "source_row_id": "F999",
            }
        ],
    )

    with pytest.raises(ValueError) as excinfo:
        lint_and_clean_structured_csvs(run_id="bad-run", output_dir=tmp_path, fixtures_dir=fixtures_dir)

    lint_report_path = tmp_path / "runs" / "bad-run" / "lint_report.json"
    assert lint_report_path.exists()
    report = json.loads(lint_report_path.read_text())
    assert report["summary"]["status"] == "failed"
    assert report["summary"]["issue_count"] == len(report["issues"]) == 3
    assert [issue["code"] for issue in report["issues"]] == [
        "UNKNOWN_FACT_SOURCE_ROW",
        "UNKNOWN_SUBJECT_ID",
        "HEADER_MISMATCH",
    ]
    assert str(lint_report_path) in str(excinfo.value)


def test_pdf_ingest_dry_run_uses_contract(tmp_path: Path):
    config = _dry_run_config(tmp_path)
    summary = run_pdf_ingest(config, run_id="test-unstructured")
    assert summary["vector_index"]["index_name"] == CHUNK_EMBEDDING_INDEX_NAME
    assert summary["vector_index"]["label"] == CHUNK_EMBEDDING_LABEL
    assert summary["vector_index"]["embedding_property"] == CHUNK_EMBEDDING_PROPERTY
    assert summary["vector_index"]["dimensions"] == CHUNK_EMBEDDING_DIMENSIONS
    assert Path(summary["ingest_summary_path"]).exists()


def test_claim_extraction_dry_run_uses_prompt_registry(tmp_path: Path):
    from demo.stages import run_claim_and_mention_extraction

    config = _dry_run_config(tmp_path)
    summary = run_claim_and_mention_extraction(config, run_id="claim-run", source_uri=None)
    assert summary["prompt_version"] == PROMPT_IDS["claim_extraction"]
    assert summary["status"] == "dry_run"


def test_claim_extraction_dry_run_includes_count_fields(tmp_path: Path):
    from demo.stages import run_claim_and_mention_extraction

    config = _dry_run_config(tmp_path)
    summary = run_claim_and_mention_extraction(config, run_id="claim-run", source_uri=None)
    assert "chunks_processed" in summary
    assert "extracted_claim_count" in summary
    assert "entity_mention_count" in summary
    assert summary["chunks_processed"] == 0
    assert summary["extracted_claim_count"] == 0
    assert summary["entity_mention_count"] == 0


def test_retrieval_and_qa_dry_run_includes_metadata_fields(tmp_path: Path):
    from demo.stages import run_retrieval_and_qa

    config = _dry_run_config(tmp_path)
    result = run_retrieval_and_qa(config, run_id="qa-run-1", source_uri="file:///example/doc.pdf", top_k=5)
    assert result["run_id"] == "qa-run-1"
    assert result["top_k"] == 5
    assert "retriever_index_name" in result
    assert result["qa_model"] == "test-model"
    assert result["qa_prompt_version"] == PROMPT_IDS["qa"]
    assert "all_answers_cited" in result
    assert isinstance(result["all_answers_cited"], bool)
    assert "citation_object_example" in result
    assert "citation_example" in result
    required_keys = {"chunk_id", "run_id", "source_uri", "chunk_index", "page", "start_char", "end_char"}
    assert required_keys.issubset(result["citation_object_example"].keys())

    # Provenance fields in citation examples must align with stage-level metadata
    assert result["citation_object_example"]["run_id"] == "qa-run-1"
    assert result["citation_object_example"]["source_uri"] == "file:///example/doc.pdf"

    # Validate citation token format: [CITATION|key=value|...], exact key/value matches for all required fields
    citation_token = result["citation_token_example"]
    assert isinstance(citation_token, str)
    assert citation_token.startswith("[CITATION|") and citation_token.endswith("]")
    inner = citation_token[1:-1]
    parts = inner.split("|")
    assert parts[0] == "CITATION"
    kv_pairs: dict[str, str] = {}
    for part in parts[1:]:
        key, sep, value = part.partition("=")
        assert sep == "=", f"Malformed citation token segment (expected key=value): {part!r}"
        kv_pairs[key] = value
    citation_obj = result["citation_object_example"]
    for key in required_keys:
        assert key in kv_pairs, f"Expected '{key}' field in citation token"
        assert kv_pairs[key] == str(citation_obj[key]), f"Expected '{key}' value {citation_obj[key]!r}, got {kv_pairs[key]!r}"


def test_retrieval_and_qa_run_id_appears_in_batch_manifest(tmp_path: Path):
    from demo.stages import run_retrieval_and_qa

    config = _dry_run_config(tmp_path)
    # Batch pipeline uses unstructured_run_id so citation examples map to stored Chunk nodes
    retrieval_stage = run_retrieval_and_qa(config, run_id="unstructured-2", source_uri=None)
    manifest = build_batch_manifest(
        config=config,
        structured_run_id="structured-1",
        unstructured_run_id="unstructured-2",
        resolution_run_id="resolution-3",
        structured_stage={"status": "dry_run"},
        pdf_stage={"status": "dry_run"},
        claim_stage={"status": "dry_run"},
        retrieval_stage=retrieval_stage,
    )
    qa_stage = manifest["stages"]["retrieval_and_qa"]
    assert qa_stage["run_id"] == "unstructured-2"
    assert qa_stage["qa_prompt_version"] == PROMPT_IDS["qa"]
    assert "citation_object_example" in qa_stage


def test_claim_extraction_dry_run_includes_chunks_with_extractions(tmp_path: Path):
    from demo.stages import run_claim_and_mention_extraction

    config = _dry_run_config(tmp_path)
    summary = run_claim_and_mention_extraction(config, run_id="claim-run", source_uri=None)
    assert "chunks_with_extractions" in summary
    assert summary["chunks_with_extractions"] == 0


def test_claim_extraction_live_path_uses_create_lexical_graph_false(tmp_path: Path):
    """Verify that _async_read_chunks_and_extract instantiates LLMEntityRelationExtractor
    with create_lexical_graph=False, enforcing the strict two-pipeline provenance contract:
    Pipeline 1 owns lexical graph creation; Pipeline 2 must only emit derived outputs
    (ExtractedClaim, EntityMention) linked to existing chunks via run_id/chunk_id."""
    from demo.stages import run_claim_and_mention_extraction

    chunk_id = "chunk-live-1"
    fake_graph = Neo4jGraph(
        nodes=[
            Neo4jNode(
                id="claim-live-1",
                label="ExtractedClaim",
                properties={"claim_text": "A live claim", "subject": "s", "predicate": "p", "object": "o"},
            ),
            Neo4jNode(
                id="mention-live-1",
                label="EntityMention",
                properties={"name": "Live Entity", "entity_type": "ORG"},
            ),
        ],
        relationships=[
            Neo4jRelationship(start_node_id=chunk_id, end_node_id="claim-live-1", type="MENTIONED_IN"),
            Neo4jRelationship(start_node_id=chunk_id, end_node_id="mention-live-1", type="MENTIONED_IN"),
        ],
    )
    fake_chunks = TextChunks(
        chunks=[TextChunk(uid=chunk_id, text="live chunk text", index=0, metadata={"run_id": "live-run"})]
    )

    # Track how LLMEntityRelationExtractor was instantiated to assert create_lexical_graph=False.
    extractor_init_kwargs: dict = {}

    class _FakeExtractor:
        def __init__(self, **kwargs):
            extractor_init_kwargs.update(kwargs)

        async def run(self, **kwargs):
            return fake_graph

    class _FakeLLM:
        def __init__(self, *args, **kwargs):
            self.async_client = mock.MagicMock()
            self.async_client.close = mock.AsyncMock()

    class _FakeChunkReader:
        def __init__(self, *args, **kwargs):
            pass

        async def run(self, **kwargs):
            return fake_chunks

    captured_write_rows: dict = {"claim_rows": [], "mention_rows": []}

    def _fake_write_extracted_rows(driver, *, neo4j_database, lexical_graph_config, claim_rows, mention_rows):
        captured_write_rows["claim_rows"] = claim_rows
        captured_write_rows["mention_rows"] = mention_rows

    config = Config(
        dry_run=False,
        output_dir=tmp_path,
        neo4j_uri="bolt://example.invalid",
        neo4j_username="neo4j",
        neo4j_password="not-used",
        neo4j_database="neo4j",
        openai_model="gpt-4o-mini",
    )

    with mock.patch(
        "neo4j_graphrag.experimental.components.entity_relation_extractor.LLMEntityRelationExtractor",
        _FakeExtractor,
    ), mock.patch(
        "neo4j_graphrag.llm.OpenAILLM",
        _FakeLLM,
    ), mock.patch(
        "demo.io.RunScopedNeo4jChunkReader",
        _FakeChunkReader,
    ), mock.patch(
        "demo.extraction_utils.write_extracted_rows",
        side_effect=_fake_write_extracted_rows,
    ), mock.patch("neo4j.GraphDatabase.driver"), mock.patch.dict(os.environ, {"OPENAI_API_KEY": "test-key"}):
        summary = run_claim_and_mention_extraction(config, run_id="live-run", source_uri="file:///doc.pdf")

    # Core assertion: the extractor must be built with create_lexical_graph=False
    assert extractor_init_kwargs.get("create_lexical_graph") is False

    assert summary["status"] == "live"
    assert summary["run_id"] == "live-run"
    assert summary["claims"] == 1
    assert summary["mentions"] == 1

    # Verify chunk-linked provenance: every extracted row must reference the source chunk_id
    assert captured_write_rows["claim_rows"][0]["chunk_ids"] == [chunk_id]
    assert captured_write_rows["mention_rows"][0]["chunk_ids"] == [chunk_id]
    assert captured_write_rows["claim_rows"][0]["run_id"] == "live-run"
    assert captured_write_rows["mention_rows"][0]["run_id"] == "live-run"


def test_retrieval_and_qa_question_recorded_in_manifest(tmp_path: Path):
    from demo.stages import run_retrieval_and_qa

    config = _dry_run_config(tmp_path)
    result = run_retrieval_and_qa(config, run_id="qa-run-2", source_uri=None, question="What happened?")
    assert result["question"] == "What happened?"


def test_retrieval_and_qa_question_none_when_not_provided(tmp_path: Path):
    from demo.stages import run_retrieval_and_qa

    config = _dry_run_config(tmp_path)
    result = run_retrieval_and_qa(config, run_id="qa-run-3", source_uri=None)
    assert result["question"] is None


def test_retrieval_and_qa_dry_run_includes_retriever_type_and_scope(tmp_path: Path):
    """Retriever type and retrieval scope metadata must always appear in stage output."""
    from demo.stages import run_retrieval_and_qa

    config = _dry_run_config(tmp_path)
    result = run_retrieval_and_qa(config, run_id="qa-run-4", source_uri="file:///doc.pdf")
    assert result["retriever_type"] == "VectorCypherRetriever"
    assert "retrieval_scope" in result
    scope = result["retrieval_scope"]
    assert scope["run_id"] == "qa-run-4"
    assert scope["source_uri"] == "file:///doc.pdf"
    assert scope["scope_widened"] is False


def test_retrieval_and_qa_dry_run_retrieval_scope_source_uri_none_when_not_provided(tmp_path: Path):
    """retrieval_scope.source_uri must be None when source_uri is not provided.
    retrieval_scope.run_id must reflect the raw run_id argument (None when omitted)."""
    from demo.stages import run_retrieval_and_qa

    config = _dry_run_config(tmp_path)
    result = run_retrieval_and_qa(config, run_id="qa-run-5", source_uri=None)
    assert result["retrieval_scope"]["source_uri"] is None
    # scope must record the actual run_id, not the citation-example placeholder
    assert result["retrieval_scope"]["run_id"] == "qa-run-5"

    # When run_id is omitted (dry-run only), retrieval_scope.run_id must be None
    result_no_run_id = run_retrieval_and_qa(config, run_id=None, source_uri=None)
    assert result_no_run_id["retrieval_scope"]["run_id"] is None


def test_retrieval_and_qa_dry_run_expand_graph_flag_recorded(tmp_path: Path):
    """expand_graph flag must be preserved in the returned stage output, and the
    retrievers list must reflect whether graph expansion was requested."""
    from demo.stages import run_retrieval_and_qa

    config = _dry_run_config(tmp_path)
    result_no_expand = run_retrieval_and_qa(config, run_id="qa-run-6", source_uri=None, expand_graph=False)
    result_expand = run_retrieval_and_qa(config, run_id="qa-run-7", source_uri=None, expand_graph=True)
    assert result_no_expand["expand_graph"] is False
    assert result_expand["expand_graph"] is True
    # retrievers list must only include "graph expansion" when expand_graph=True
    assert "graph expansion" not in result_no_expand["retrievers"]
    assert "graph expansion" in result_expand["retrievers"]


def _make_fake_retriever_result(items):
    """Build a minimal fake RawSearchResult-like object with an .items attribute."""

    class _FakeResult:
        def __init__(self, items):
            self.items = items

    return _FakeResult(items)


def _make_fake_retriever_result_item(content, metadata):
    """Build a RetrieverResultItem-compatible object."""
    from neo4j_graphrag.types import RetrieverResultItem

    return RetrieverResultItem(content=content, metadata=metadata)


def _make_fake_rag_result(items, answer: str = ""):
    """Build a minimal fake RagResultModel-like object that GraphRAG.search() returns.

    The `retriever_result` must expose `.items` so the live path can iterate results.
    """

    class _FakeRetrieverResult:
        def __init__(self, items):
            self.items = items

    class _FakeRagResult:
        def __init__(self, items, answer):
            self.answer = answer
            self.retriever_result = _FakeRetrieverResult(items)

    return _FakeRagResult(items, answer)


def _make_stub_graphrag_class(answer: str = "", capture: dict | None = None):
    """Return a GraphRAG stub class that bypasses Pydantic validation.

    The stub's ``search()`` method calls the fake retriever's ``search()``
    with ``query_params`` extracted from ``retriever_config`` so that tests
    can still inspect ``captured_search`` / ``captured_params`` populated by
    the fake retriever.

    When *capture* is provided it is populated with the constructor arguments
    (``llm``, ``prompt_template``) and each search call's ``message_history``
    so tests can assert on those values without duplicating stub logic.
    """

    class _FakeGraphRAG:
        def __init__(self, *, retriever, llm, prompt_template=None):
            self._retriever = retriever
            if capture is not None:
                capture["llm"] = llm
                capture["prompt_template"] = prompt_template

        def search(self, *, query_text="", retriever_config=None, return_context=None, message_history=None, **kwargs):
            cfg = retriever_config or {}
            if capture is not None:
                capture["message_history"] = message_history
            result = self._retriever.search(
                query_text=query_text,
                top_k=cfg.get("top_k"),
                query_params=cfg.get("query_params"),
            )
            return _make_fake_rag_result(result.items, answer=answer)

    return _FakeGraphRAG

def test_retrieval_and_qa_live_path_uses_vector_cypher_retriever(tmp_path: Path):
    """Live path must instantiate VectorCypherRetriever with the correct index and call search
    with run_id in query_params for run-scoped retrieval. OpenAIEmbeddings must use the
    contract's embedder model name."""
    from demo.stages import run_retrieval_and_qa
    from demo.stages.retrieval_and_qa import _chunk_citation_formatter
    from demo.contracts.pipeline import EMBEDDER_MODEL_NAME

    captured_init: dict = {}
    captured_search: dict = {}
    captured_embedder_args: list = []

    class _FakeEmbedder:
        def __init__(self, *args, **kwargs):
            captured_embedder_args.append((args, kwargs))

    class _FakeRetriever:
        def __init__(self, **kwargs):
            captured_init.update(kwargs)

        def search(self, **kwargs):
            captured_search.update(kwargs)
            return _make_fake_retriever_result([])

    live_config = Config(
        dry_run=False,
        output_dir=tmp_path,
        neo4j_uri="bolt://example.invalid",
        neo4j_username="neo4j",
        neo4j_password="not-used",
        neo4j_database="neo4j",
        openai_model="gpt-4o-mini",
    )

    # GraphRAG is patched via the shared helper to bypass Pydantic retriever
    # validation while still delegating search() to the fake retriever so
    # captured_search is populated.
    _StubGraphRAG = _make_stub_graphrag_class()

    with mock.patch("demo.stages.retrieval_and_qa.VectorCypherRetriever", _FakeRetriever), mock.patch(
        "demo.stages.retrieval_and_qa.OpenAIEmbeddings", _FakeEmbedder
    ), mock.patch("demo.stages.retrieval_and_qa.GraphRAG", _StubGraphRAG), mock.patch(
        "demo.stages.retrieval_and_qa.OpenAILLM"
    ), mock.patch("neo4j.GraphDatabase.driver"), mock.patch.dict(os.environ, {"OPENAI_API_KEY": "test-key"}):
        result = run_retrieval_and_qa(
            live_config,
            run_id="live-run-1",
            source_uri="file:///doc.pdf",
            top_k=3,
            question="What happened?",
        )

    assert captured_init["index_name"] == CHUNK_EMBEDDING_INDEX_NAME
    assert captured_init["result_formatter"] is _chunk_citation_formatter
    assert captured_search["query_text"] == "What happened?"
    assert captured_search["top_k"] == 3
    assert captured_search["query_params"]["run_id"] == "live-run-1"
    assert captured_search["query_params"]["source_uri"] == "file:///doc.pdf"
    assert result["status"] == "live"
    assert result["hits"] == 0
    assert result["retrieval_results"] == []
    assert result["warnings"] == []
    # "graph expansion" must NOT appear in retrievers when expand_graph=False
    assert "graph expansion" not in result["retrievers"]
    # Embedder must use the contract's model name to match the index dimensions
    assert len(captured_embedder_args) == 1
    assert captured_embedder_args[0][1].get("model") == EMBEDDER_MODEL_NAME


def test_retrieval_and_qa_live_path_formats_citation_tokens(tmp_path: Path):
    """Live path must produce citation tokens from retrieved Chunk records and update
    citation_token_example / citation_object_example with actual first-hit provenance."""
    from demo.stages import run_retrieval_and_qa

    fake_meta = {
        "chunk_id": "chunk-abc",
        "run_id": "live-run-2",
        "source_uri": "file:///doc.pdf",
        "chunk_index": 3,
        "page": 2,
        "start_char": 100,
        "end_char": 500,
        "score": 0.95,
        "citation_token": (
            "[CITATION|chunk_id=chunk-abc|run_id=live-run-2|"
            "source_uri=file:///doc.pdf|chunk_index=3|page=2|start_char=100|end_char=500]"
        ),
        "citation_object": {
            "chunk_id": "chunk-abc",
            "run_id": "live-run-2",
            "source_uri": "file:///doc.pdf",
            "chunk_index": 3,
            "page": 2,
            "start_char": 100,
            "end_char": 500,
        },
    }
    fake_item = _make_fake_retriever_result_item(
        content="Chunk text.\n" + fake_meta["citation_token"],
        metadata=fake_meta,
    )

    class _FakeRetriever:
        def __init__(self, **kwargs):
            pass

        def search(self, **kwargs):
            return _make_fake_retriever_result([fake_item])

    live_config = Config(
        dry_run=False,
        output_dir=tmp_path,
        neo4j_uri="bolt://example.invalid",
        neo4j_username="neo4j",
        neo4j_password="not-used",
        neo4j_database="neo4j",
        openai_model="gpt-4o-mini",
    )

    with mock.patch("demo.stages.retrieval_and_qa.VectorCypherRetriever", _FakeRetriever), mock.patch(
        "demo.stages.retrieval_and_qa.OpenAIEmbeddings"
    ), mock.patch("demo.stages.retrieval_and_qa.GraphRAG", _make_stub_graphrag_class()), mock.patch(
        "demo.stages.retrieval_and_qa.OpenAILLM"
    ), mock.patch("neo4j.GraphDatabase.driver"), mock.patch.dict(os.environ, {"OPENAI_API_KEY": "test-key"}):
        result = run_retrieval_and_qa(
            live_config,
            run_id="live-run-2",
            source_uri="file:///doc.pdf",
            top_k=5,
            question="What is chain of custody?",
        )

    assert result["status"] == "live"
    assert result["hits"] == 1
    assert len(result["retrieval_results"]) == 1
    assert result["warnings"] == []

    # citation_token_example and citation_object_example must reflect actual hit provenance
    assert result["citation_token_example"] == fake_meta["citation_token"]
    assert result["citation_object_example"]["chunk_id"] == "chunk-abc"
    assert result["citation_object_example"]["run_id"] == "live-run-2"
    assert result["citation_object_example"]["page"] == 2


def test_retrieval_and_qa_live_path_no_question_returns_empty_hits(tmp_path: Path):
    """Live path without a question must return empty hits immediately without opening
    a Neo4j driver or instantiating an embedder.  retrievers must be empty (nothing ran),
    retrieval_skipped must be True, and the skip warning must appear in warnings.
    Importantly, the skip path must work even with invalid/empty Neo4j credentials."""
    from demo.stages import run_retrieval_and_qa

    # Use empty Neo4j credentials to prove the skip path doesn't touch them.
    live_config = Config(
        dry_run=False,
        output_dir=tmp_path,
        neo4j_uri="",
        neo4j_username="",
        neo4j_password="",
        neo4j_database="",
        openai_model="gpt-4o-mini",
    )

    # No driver or embedder patches needed — the function must return before touching them.
    result = run_retrieval_and_qa(live_config, run_id="live-run-3", source_uri=None, question=None)

    assert result["status"] == "live"
    assert result["hits"] == 0
    assert result["retrieval_results"] == []
    # No retrieval ran, so retrievers must be empty
    assert result["retrievers"] == []
    # retrieval_skipped flag must signal that the retrieval step was bypassed
    assert result["retrieval_skipped"] is True
    # The skip warning must be surfaced in the warnings list
    assert any("No question" in w for w in result["warnings"])


def test_retrieval_and_qa_live_path_requires_run_id(tmp_path: Path):
    """Live path must raise ValueError when run_id is omitted to prevent silent cross-run retrieval."""
    from demo.stages import run_retrieval_and_qa

    live_config = Config(
        dry_run=False,
        output_dir=tmp_path,
        neo4j_uri="bolt://example.invalid",
        neo4j_username="neo4j",
        neo4j_password="not-used",
        neo4j_database="neo4j",
        openai_model="gpt-4o-mini",
    )

    with pytest.raises(ValueError, match="run_id is required"):
        run_retrieval_and_qa(live_config, run_id=None, source_uri=None, question="Test?")


def test_retrieval_and_qa_live_path_requires_openai_api_key(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """Live path must raise ValueError when OPENAI_API_KEY is missing (after the question=None skip path)."""
    import os

    from demo.stages import run_retrieval_and_qa

    monkeypatch.delitem(os.environ, "OPENAI_API_KEY", raising=False)

    live_config = Config(
        dry_run=False,
        output_dir=tmp_path,
        neo4j_uri="bolt://example.invalid",
        neo4j_username="neo4j",
        neo4j_password="not-used",
        neo4j_database="neo4j",
        openai_model="gpt-4o-mini",
    )

    with pytest.raises(ValueError, match="OPENAI_API_KEY"):
        run_retrieval_and_qa(live_config, run_id="live-run-key", source_uri=None, question="Test?")


def test_retrieval_and_qa_live_path_warns_on_missing_citation_fields(tmp_path: Path):
    """Live path must record warnings for chunks missing optional citation fields (page, start_char, end_char)."""
    from demo.stages import run_retrieval_and_qa

    # Simulate a chunk with no page/start_char/end_char
    fake_meta_missing = {
        "chunk_id": "chunk-no-page",
        "run_id": "live-run-4",
        "source_uri": "file:///doc.pdf",
        "chunk_index": 0,
        "page": None,
        "start_char": None,
        "end_char": None,
        "score": 0.8,
        "citation_token": (
            "[CITATION|chunk_id=chunk-no-page|run_id=live-run-4|"
            "source_uri=file:///doc.pdf|chunk_index=0|page=None|start_char=None|end_char=None]"
        ),
        "citation_object": {
            "chunk_id": "chunk-no-page",
            "run_id": "live-run-4",
            "source_uri": "file:///doc.pdf",
            "chunk_index": 0,
            "page": None,
            "start_char": None,
            "end_char": None,
        },
    }
    fake_item = _make_fake_retriever_result_item(
        content="Chunk text.\n" + fake_meta_missing["citation_token"],
        metadata=fake_meta_missing,
    )

    class _FakeRetriever:
        def __init__(self, **kwargs):
            pass

        def search(self, **kwargs):
            return _make_fake_retriever_result([fake_item])

    live_config = Config(
        dry_run=False,
        output_dir=tmp_path,
        neo4j_uri="bolt://example.invalid",
        neo4j_username="neo4j",
        neo4j_password="not-used",
        neo4j_database="neo4j",
        openai_model="gpt-4o-mini",
    )

    with mock.patch("demo.stages.retrieval_and_qa.VectorCypherRetriever", _FakeRetriever), mock.patch(
        "demo.stages.retrieval_and_qa.OpenAIEmbeddings"
    ), mock.patch("demo.stages.retrieval_and_qa.GraphRAG", _make_stub_graphrag_class()), mock.patch(
        "demo.stages.retrieval_and_qa.OpenAILLM"
    ), mock.patch("neo4j.GraphDatabase.driver"), mock.patch.dict(os.environ, {"OPENAI_API_KEY": "test-key"}):
        result = run_retrieval_and_qa(
            live_config,
            run_id="live-run-4",
            source_uri="file:///doc.pdf",
            top_k=5,
            question="What happened?",
        )

    assert result["status"] == "live"
    assert result["hits"] == 1
    # Warnings must be non-empty and mention the chunk_id
    assert len(result["warnings"]) > 0
    assert any("chunk-no-page" in w for w in result["warnings"])


def test_retrieval_and_qa_live_path_run_scoped_by_default(tmp_path: Path):
    """Retrieval scope must be run_id-scoped by default; source_uri=None means no source filtering."""
    from demo.stages import run_retrieval_and_qa

    captured_params: dict = {}

    class _FakeRetriever:
        def __init__(self, **kwargs):
            pass

        def search(self, **kwargs):
            captured_params.update(kwargs.get("query_params", {}))
            return _make_fake_retriever_result([])

    live_config = Config(
        dry_run=False,
        output_dir=tmp_path,
        neo4j_uri="bolt://example.invalid",
        neo4j_username="neo4j",
        neo4j_password="not-used",
        neo4j_database="neo4j",
        openai_model="gpt-4o-mini",
    )

    with mock.patch("demo.stages.retrieval_and_qa.VectorCypherRetriever", _FakeRetriever), mock.patch(
        "demo.stages.retrieval_and_qa.OpenAIEmbeddings"
    ), mock.patch("demo.stages.retrieval_and_qa.GraphRAG", _make_stub_graphrag_class()), mock.patch(
        "demo.stages.retrieval_and_qa.OpenAILLM"
    ), mock.patch("neo4j.GraphDatabase.driver"), mock.patch.dict(os.environ, {"OPENAI_API_KEY": "test-key"}):
        run_retrieval_and_qa(
            live_config,
            run_id="scoped-run",
            source_uri=None,
            question="Test question",
        )

    # run_id must always be in query params (run-scoped by default)
    assert captured_params["run_id"] == "scoped-run"
    # source_uri=None means cross-source retrieval within the run (no narrowing)
    assert captured_params["source_uri"] is None


def test_retrieval_and_qa_live_path_uses_expanded_query_when_expand_graph(tmp_path: Path):
    """When expand_graph=True, the retriever must be initialised with the expansion query."""
    from demo.stages import run_retrieval_and_qa
    from demo.stages.retrieval_and_qa import _RETRIEVAL_QUERY_WITH_EXPANSION

    captured_init: dict = {}

    class _FakeRetriever:
        def __init__(self, **kwargs):
            captured_init.update(kwargs)

        def search(self, **kwargs):
            return _make_fake_retriever_result([])

    live_config = Config(
        dry_run=False,
        output_dir=tmp_path,
        neo4j_uri="bolt://example.invalid",
        neo4j_username="neo4j",
        neo4j_password="not-used",
        neo4j_database="neo4j",
        openai_model="gpt-4o-mini",
    )

    with mock.patch("demo.stages.retrieval_and_qa.VectorCypherRetriever", _FakeRetriever), mock.patch(
        "demo.stages.retrieval_and_qa.OpenAIEmbeddings"
    ), mock.patch("demo.stages.retrieval_and_qa.GraphRAG", _make_stub_graphrag_class()), mock.patch(
        "demo.stages.retrieval_and_qa.OpenAILLM"
    ), mock.patch("neo4j.GraphDatabase.driver"), mock.patch.dict(os.environ, {"OPENAI_API_KEY": "test-key"}):
        result = run_retrieval_and_qa(
            live_config,
            run_id="expand-run",
            source_uri=None,
            question="Test",
            expand_graph=True,
        )

    assert captured_init["retrieval_query"] == _RETRIEVAL_QUERY_WITH_EXPANSION
    assert result["expand_graph"] is True
    # retrievers list must include "graph expansion" when expand_graph=True
    assert "graph expansion" in result["retrievers"]


def test_build_citation_token_format():
    """_build_citation_token must produce a stable [CITATION|key=value|...] token."""
    from demo.stages.retrieval_and_qa import _build_citation_token

    token = _build_citation_token(
        chunk_id="c1",
        run_id="r1",
        source_uri="file:///doc.pdf",
        chunk_index=2,
        page=3,
        start_char=10,
        end_char=200,
    )
    assert token == (
        "[CITATION|chunk_id=c1|run_id=r1|source_uri=file:///doc.pdf|chunk_index=2|page=3|start_char=10|end_char=200]"
    )


def test_build_citation_token_encodes_delimiter_chars():
    """_build_citation_token must percent-encode '|', ']', and '%' in field values so
    that downstream parsing (splitting on '|' and ']') is always safe."""
    from demo.stages.retrieval_and_qa import _build_citation_token

    # source_uri with a pipe character (e.g. some non-file URI or unusual path)
    token = _build_citation_token(
        chunk_id="c|1",
        run_id="r]1",
        source_uri="file:///path%7Cwith|pipe.pdf",
        chunk_index=0,
        page=None,
        start_char=None,
        end_char=None,
    )
    # The token must not contain a raw '|' inside any value (only between keys),
    # and must not contain a raw ']' except at the very end.
    inner = token[len("[CITATION|"):-1]
    parts = inner.split("|")
    # We should have exactly 7 key=value parts
    assert len(parts) == 7, f"Unexpected parts: {parts}"
    # chunk_id '|' encoded to %7C
    assert parts[0] == "chunk_id=c%7C1"
    # run_id ']' encoded to %5D
    assert parts[1] == "run_id=r%5D1"
    # source_uri '%' encoded to %25, then '|' encoded to %7C
    assert parts[2] == "source_uri=file:///path%257Cwith%7Cpipe.pdf"
    # token must still end with ']'
    assert token.endswith("]")


# ---------------------------------------------------------------------------
# New tests: GraphRAG Q&A prompt template, answer generation, citation check,
# message history, interactive mode, and manifest fields from issue #156.
# ---------------------------------------------------------------------------


def test_power_atlas_rag_template_enforces_citation_instructions():
    """The Power Atlas RagTemplate must include citation-enforcement instructions."""
    from demo.contracts.prompts import POWER_ATLAS_RAG_TEMPLATE

    tmpl = POWER_ATLAS_RAG_TEMPLATE.template
    assert "[CITATION|" in tmpl, "Template must reference citation token format"
    assert "context" in tmpl.lower(), "Template must reference context"
    assert "insuffic" in tmpl.lower() or "insufficient" in tmpl.lower(), (
        "Template must mention insufficient context handling"
    )
    assert "conflict" in tmpl.lower(), "Template must mention conflicting evidence handling"


def test_power_atlas_rag_template_uses_vendor_rag_template_class():
    """Power Atlas template must extend the vendor RagTemplate for GraphRAG wiring."""
    from neo4j_graphrag.generation import RagTemplate
    from demo.contracts.prompts import POWER_ATLAS_RAG_TEMPLATE

    assert isinstance(POWER_ATLAS_RAG_TEMPLATE, RagTemplate)


def test_power_atlas_rag_template_prompt_id_updated():
    """qa prompt ID must reflect the updated prompt version (qa_v2)."""
    from demo.contracts.prompts import PROMPT_IDS

    assert PROMPT_IDS["qa"] == "qa_v2", (
        "PROMPT_IDS['qa'] must be updated to 'qa_v2' to reflect the new citation-enforcing template"
    )


def test_check_all_answers_cited_fully_cited():
    """_check_all_answers_cited must return True when every sentence has a citation token."""
    from demo.stages.retrieval_and_qa import _check_all_answers_cited

    answer = (
        "The chain of custody was established in 2021. [CITATION|chunk_id=c1|run_id=r1|source_uri=file:///x.pdf|"
        "chunk_index=0|page=1|start_char=0|end_char=100]\n"
        "Evidence was collected from the scene. [CITATION|chunk_id=c2|run_id=r1|source_uri=file:///x.pdf|"
        "chunk_index=1|page=2|start_char=100|end_char=200]"
    )
    assert _check_all_answers_cited(answer) is True


def test_check_all_answers_cited_uncited_sentence():
    """_check_all_answers_cited must return False when any sentence lacks a citation."""
    from demo.stages.retrieval_and_qa import _check_all_answers_cited

    answer = (
        "The chain of custody was established in 2021. [CITATION|chunk_id=c1|run_id=r1|source_uri=file:///x.pdf|"
        "chunk_index=0|page=1|start_char=0|end_char=100]\n"
        "This claim has no citation."
    )
    assert _check_all_answers_cited(answer) is False


def test_check_all_answers_cited_empty_answer():
    """_check_all_answers_cited must return False for an empty answer string."""
    from demo.stages.retrieval_and_qa import _check_all_answers_cited

    assert _check_all_answers_cited("") is False
    assert _check_all_answers_cited("   ") is False


def test_check_all_answers_cited_requires_token_at_end_of_line():
    """_check_all_answers_cited must return False when a citation token appears on a line
    but does not close it (i.e. additional text follows the token), catching the false-positive
    case where a line has multiple sentences but only the first is cited."""
    from demo.stages.retrieval_and_qa import _check_all_answers_cited

    # Citation token is present but is not at the end of the line
    answer = (
        "[CITATION|chunk_id=c1|run_id=r1|source_uri=file:///x.pdf|"
        "chunk_index=0|page=1|start_char=0|end_char=50] And this second sentence is uncited."
    )
    assert _check_all_answers_cited(answer) is False


def test_check_all_answers_cited_rejects_non_citation_trailing_bracket():
    """_check_all_answers_cited must return False when a line ends with ']' but the
    bracket is not part of a [CITATION|...] token (e.g. a Markdown link or annotation)."""
    from demo.stages.retrieval_and_qa import _check_all_answers_cited

    # Line ends with ] from a Markdown link, not a citation token
    answer = "See the [documentation](https://example.com/docs)"
    assert _check_all_answers_cited(answer) is False

    # Line ends with ] from some other annotation
    answer = "Evidence was collected. [Note: see appendix]"
    assert _check_all_answers_cited(answer) is False


def test_check_all_answers_cited_accepts_multiple_trailing_tokens():
    """_check_all_answers_cited must return True when a line ends with multiple consecutive
    [CITATION|...] tokens (multi-source claim)."""
    from demo.stages.retrieval_and_qa import _check_all_answers_cited

    answer = (
        "Evidence was collected on-site. "
        "[CITATION|chunk_id=c1|run_id=r1|source_uri=file:///x.pdf|chunk_index=0|page=1|start_char=0|end_char=50]"
        "[CITATION|chunk_id=c2|run_id=r1|source_uri=file:///x.pdf|chunk_index=1|page=2|start_char=51|end_char=100]"
    )
    assert _check_all_answers_cited(answer) is True

def test_retrieval_and_qa_dry_run_includes_interactive_mode_flag(tmp_path: Path):
    """Dry-run result must record interactive_mode and message_history_enabled flags."""
    from demo.stages import run_retrieval_and_qa

    config = _dry_run_config(tmp_path)
    result = run_retrieval_and_qa(config, run_id="qa-run-im", source_uri=None, interactive=True)
    assert result["interactive_mode"] is True
    assert result["message_history_enabled"] is False

    result_no_interactive = run_retrieval_and_qa(config, run_id="qa-run-ni", source_uri=None)
    assert result_no_interactive["interactive_mode"] is False


def test_retrieval_and_qa_live_path_records_answer_and_all_answers_cited(tmp_path: Path):
    """Live path must return an 'answer' key and set all_answers_cited=True when
    the generated answer contains citation tokens in every sentence."""
    from demo.stages import run_retrieval_and_qa

    cited_answer = (
        "Evidence was found. [CITATION|chunk_id=c1|run_id=live-run-cited|"
        "source_uri=file:///x.pdf|chunk_index=0|page=1|start_char=0|end_char=50]"
    )

    class _FakeRetriever:
        def __init__(self, **kwargs):
            pass

        def search(self, **kwargs):
            return _make_fake_retriever_result([])

    live_config = Config(
        dry_run=False,
        output_dir=tmp_path,
        neo4j_uri="bolt://example.invalid",
        neo4j_username="neo4j",
        neo4j_password="not-used",
        neo4j_database="neo4j",
        openai_model="gpt-4o-mini",
    )

    with mock.patch("demo.stages.retrieval_and_qa.VectorCypherRetriever", _FakeRetriever), mock.patch(
        "demo.stages.retrieval_and_qa.OpenAIEmbeddings"
    ), mock.patch("demo.stages.retrieval_and_qa.GraphRAG", _make_stub_graphrag_class(answer=cited_answer)), mock.patch(
        "demo.stages.retrieval_and_qa.OpenAILLM"
    ), mock.patch("neo4j.GraphDatabase.driver"), mock.patch.dict(os.environ, {"OPENAI_API_KEY": "test-key"}):
        result = run_retrieval_and_qa(
            live_config,
            run_id="live-run-cited",
            source_uri=None,
            question="What happened?",
        )

    assert result["answer"] == cited_answer
    assert result["all_answers_cited"] is True
    # No citation-completeness warning when all sentences are cited
    assert not any("citation" in w.lower() for w in result["warnings"])


def test_retrieval_and_qa_live_path_records_warning_when_uncited(tmp_path: Path):
    """Live path must set all_answers_cited=False and add a warning when the answer
    contains sentences without citation tokens."""
    from demo.stages import run_retrieval_and_qa

    uncited_answer = "This claim has no citation and is not grounded."

    class _FakeRetriever:
        def __init__(self, **kwargs):
            pass

        def search(self, **kwargs):
            return _make_fake_retriever_result([])

    live_config = Config(
        dry_run=False,
        output_dir=tmp_path,
        neo4j_uri="bolt://example.invalid",
        neo4j_username="neo4j",
        neo4j_password="not-used",
        neo4j_database="neo4j",
        openai_model="gpt-4o-mini",
    )

    with mock.patch("demo.stages.retrieval_and_qa.VectorCypherRetriever", _FakeRetriever), mock.patch(
        "demo.stages.retrieval_and_qa.OpenAIEmbeddings"
    ), mock.patch("demo.stages.retrieval_and_qa.GraphRAG", _make_stub_graphrag_class(answer=uncited_answer)), mock.patch(
        "demo.stages.retrieval_and_qa.OpenAILLM"
    ), mock.patch("neo4j.GraphDatabase.driver"), mock.patch.dict(os.environ, {"OPENAI_API_KEY": "test-key"}):
        result = run_retrieval_and_qa(
            live_config,
            run_id="live-run-uncited",
            source_uri=None,
            question="What happened?",
        )

    assert result["all_answers_cited"] is False
    assert any("citation" in w.lower() for w in result["warnings"])

def test_retrieval_and_qa_live_path_passes_message_history_to_graphrag(tmp_path: Path):
    """When message_history is provided, it must be forwarded to GraphRAG.search() and
    message_history_enabled must be True in the result."""
    from demo.stages import run_retrieval_and_qa
    from neo4j_graphrag.message_history import InMemoryMessageHistory

    captured_rag_search_args: dict = {}

    class _FakeRetriever:
        def __init__(self, **kwargs):
            pass

        def search(self, **kwargs):
            return _make_fake_retriever_result([])

    live_config = Config(
        dry_run=False,
        output_dir=tmp_path,
        neo4j_uri="bolt://example.invalid",
        neo4j_username="neo4j",
        neo4j_password="not-used",
        neo4j_database="neo4j",
        openai_model="gpt-4o-mini",
    )

    history = InMemoryMessageHistory()

    with mock.patch("demo.stages.retrieval_and_qa.VectorCypherRetriever", _FakeRetriever), mock.patch(
        "demo.stages.retrieval_and_qa.OpenAIEmbeddings"
    ), mock.patch("demo.stages.retrieval_and_qa.GraphRAG", _make_stub_graphrag_class(capture=captured_rag_search_args)), mock.patch(
        "demo.stages.retrieval_and_qa.OpenAILLM"
    ), mock.patch("neo4j.GraphDatabase.driver"), mock.patch.dict(os.environ, {"OPENAI_API_KEY": "test-key"}):
        result = run_retrieval_and_qa(
            live_config,
            run_id="live-run-hist",
            source_uri=None,
            question="Follow-up question?",
            message_history=history,
            interactive=True,
        )

    assert result["message_history_enabled"] is True
    assert result["interactive_mode"] is True
    assert captured_rag_search_args["message_history"] is history


def test_retrieval_and_qa_live_path_uses_openai_llm_with_model_from_config(tmp_path: Path):
    """Live path must create OpenAILLM with the model from config and temperature=0."""
    from demo.stages import run_retrieval_and_qa

    captured_llm_args: dict = {}

    class _FakeRetriever:
        def __init__(self, **kwargs):
            pass

        def search(self, **kwargs):
            return _make_fake_retriever_result([])

    class _FakeLLM:
        def __init__(self, model_name, model_params=None):
            captured_llm_args["model_name"] = model_name
            captured_llm_args["model_params"] = model_params

    live_config = Config(
        dry_run=False,
        output_dir=tmp_path,
        neo4j_uri="bolt://example.invalid",
        neo4j_username="neo4j",
        neo4j_password="not-used",
        neo4j_database="neo4j",
        openai_model="gpt-4o",
    )

    with mock.patch("demo.stages.retrieval_and_qa.VectorCypherRetriever", _FakeRetriever), mock.patch(
        "demo.stages.retrieval_and_qa.OpenAIEmbeddings"
    ), mock.patch("demo.stages.retrieval_and_qa.GraphRAG", _make_stub_graphrag_class()), mock.patch(
        "demo.stages.retrieval_and_qa.OpenAILLM", _FakeLLM
    ), mock.patch("neo4j.GraphDatabase.driver"), mock.patch.dict(os.environ, {"OPENAI_API_KEY": "test-key"}):
        run_retrieval_and_qa(
            live_config,
            run_id="live-run-llm",
            source_uri=None,
            question="Test question",
        )

    assert captured_llm_args["model_name"] == "gpt-4o"
    assert captured_llm_args["model_params"] == {"temperature": 0}


def test_retrieval_and_qa_live_path_uses_power_atlas_prompt_template(tmp_path: Path):
    """Live path must pass the Power Atlas citation-enforcing prompt template to GraphRAG."""
    from demo.stages import run_retrieval_and_qa
    from demo.contracts.prompts import POWER_ATLAS_RAG_TEMPLATE

    captured_prompt: dict = {}

    class _FakeRetriever:
        def __init__(self, **kwargs):
            pass

        def search(self, **kwargs):
            return _make_fake_retriever_result([])

    live_config = Config(
        dry_run=False,
        output_dir=tmp_path,
        neo4j_uri="bolt://example.invalid",
        neo4j_username="neo4j",
        neo4j_password="not-used",
        neo4j_database="neo4j",
        openai_model="gpt-4o-mini",
    )

    with mock.patch("demo.stages.retrieval_and_qa.VectorCypherRetriever", _FakeRetriever), mock.patch(
        "demo.stages.retrieval_and_qa.OpenAIEmbeddings"
    ), mock.patch("demo.stages.retrieval_and_qa.GraphRAG", _make_stub_graphrag_class(capture=captured_prompt)), mock.patch(
        "demo.stages.retrieval_and_qa.OpenAILLM"
    ), mock.patch("neo4j.GraphDatabase.driver"), mock.patch.dict(os.environ, {"OPENAI_API_KEY": "test-key"}):
        run_retrieval_and_qa(
            live_config,
            run_id="live-run-prompt",
            source_uri=None,
            question="Test question",
        )

    assert captured_prompt["prompt_template"] is POWER_ATLAS_RAG_TEMPLATE


def test_ask_interactive_rejects_dry_run(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """CLI 'ask --interactive' must raise SystemExit when config.dry_run=True so the user
    is not silently presented with empty answers instead of an error."""
    import sys
    from demo.run_demo import main

    monkeypatch.setenv("UNSTRUCTURED_RUN_ID", "test-run-id")
    monkeypatch.setattr(sys, "argv", ["demo", "--dry-run", "ask", "--interactive"])
    with pytest.raises(SystemExit) as exc_info:
        main()
    # Must exit with a message referencing --live (not a clean 0 exit)
    assert "live" in str(exc_info.value).lower() or exc_info.value.code not in (0, None)


def test_retrieval_and_qa_live_path_qa_model_never_none(tmp_path: Path):
    """The manifest's qa_model must never be None: when config.openai_model is not set,
    the fallback default must be recorded in the result."""
    from demo.stages import run_retrieval_and_qa

    class _FakeRetriever:
        def __init__(self, **kwargs):
            pass

        def search(self, **kwargs):
            return _make_fake_retriever_result([])

    # Config with openai_model explicitly None (simulating unset)
    no_model_config = Config(
        dry_run=False,
        output_dir=tmp_path,
        neo4j_uri="bolt://example.invalid",
        neo4j_username="neo4j",
        neo4j_password="not-used",
        neo4j_database="neo4j",
        openai_model="",  # empty string -> falsy, triggers fallback
    )

    with mock.patch("demo.stages.retrieval_and_qa.VectorCypherRetriever", _FakeRetriever), mock.patch(
        "demo.stages.retrieval_and_qa.OpenAIEmbeddings"
    ), mock.patch("demo.stages.retrieval_and_qa.GraphRAG", _make_stub_graphrag_class()), mock.patch(
        "demo.stages.retrieval_and_qa.OpenAILLM"
    ), mock.patch("neo4j.GraphDatabase.driver"), mock.patch.dict(os.environ, {"OPENAI_API_KEY": "test-key"}):
        result = run_retrieval_and_qa(
            no_model_config,
            run_id="live-run-no-model",
            source_uri=None,
            question="Test?",
        )

    assert result["qa_model"] is not None
    assert result["qa_model"] != ""
    assert result["qa_model"] == "gpt-4o-mini"


def test_run_interactive_qa_prints_citation_warning_when_uncited(
    tmp_path: Path, capsys: pytest.CaptureFixture
):
    """run_interactive_qa must print a visible citation warning to stdout when the
    answer contains lines without citation tokens (degraded evidence quality)."""
    from demo.stages.retrieval_and_qa import run_interactive_qa

    uncited_answer = "This claim has no citation and is not grounded."

    class _FakeRetriever:
        def __init__(self, **kwargs):
            pass

        def search(self, **kwargs):
            return _make_fake_retriever_result([])

    # Stub GraphRAG to return an uncited answer on the first question, then simulate EOF
    call_count = {"n": 0}

    class _FakeGraphRAG:
        def __init__(self, *, retriever, llm, prompt_template=None):
            pass

        def search(self, *, query_text="", retriever_config=None, return_context=None, message_history=None, **kwargs):
            call_count["n"] += 1
            return _make_fake_rag_result([], answer=uncited_answer)

    live_config = Config(
        dry_run=False,
        output_dir=tmp_path,
        neo4j_uri="bolt://example.invalid",
        neo4j_username="neo4j",
        neo4j_password="not-used",
        neo4j_database="neo4j",
        openai_model="gpt-4o-mini",
    )

    # Simulate one question then EOF so the REPL exits cleanly.
    inputs = iter(["What happened?"])

    def _fake_input(_prompt=""):
        try:
            return next(inputs)
        except StopIteration:
            raise EOFError

    with mock.patch("demo.stages.retrieval_and_qa.VectorCypherRetriever", _FakeRetriever), mock.patch(
        "demo.stages.retrieval_and_qa.OpenAIEmbeddings"
    ), mock.patch("demo.stages.retrieval_and_qa.GraphRAG", _FakeGraphRAG), mock.patch(
        "demo.stages.retrieval_and_qa.OpenAILLM"
    ), mock.patch("neo4j.GraphDatabase.driver"), mock.patch.dict(
        os.environ, {"OPENAI_API_KEY": "test-key"}
    ), mock.patch("builtins.input", _fake_input):
        run_interactive_qa(live_config, run_id="interactive-run-uncited")

    captured = capsys.readouterr()
    assert "WARNING" in captured.out
    assert "cited" in captured.out.lower() or "citation" in captured.out.lower()
    assert "degraded" in captured.out.lower()


def test_run_interactive_qa_no_warning_when_fully_cited(
    tmp_path: Path, capsys: pytest.CaptureFixture
):
    """run_interactive_qa must NOT print a citation warning when every answer line is cited."""
    from demo.stages.retrieval_and_qa import run_interactive_qa

    cited_answer = "All claims are supported. [CITATION|chunk_id=c1|run_id=r1|source_uri=file:///doc.pdf|chunk_index=0|page=1|start_char=0|end_char=10]"

    class _FakeRetriever:
        def __init__(self, **kwargs):
            pass

        def search(self, **kwargs):
            return _make_fake_retriever_result([])

    class _FakeGraphRAG:
        def __init__(self, *, retriever, llm, prompt_template=None):
            pass

        def search(self, *, query_text="", retriever_config=None, return_context=None, message_history=None, **kwargs):
            return _make_fake_rag_result([], answer=cited_answer)

    live_config = Config(
        dry_run=False,
        output_dir=tmp_path,
        neo4j_uri="bolt://example.invalid",
        neo4j_username="neo4j",
        neo4j_password="not-used",
        neo4j_database="neo4j",
        openai_model="gpt-4o-mini",
    )

    inputs = iter(["What happened?"])

    def _fake_input(_prompt=""):
        try:
            return next(inputs)
        except StopIteration:
            raise EOFError

    with mock.patch("demo.stages.retrieval_and_qa.VectorCypherRetriever", _FakeRetriever), mock.patch(
        "demo.stages.retrieval_and_qa.OpenAIEmbeddings"
    ), mock.patch("demo.stages.retrieval_and_qa.GraphRAG", _FakeGraphRAG), mock.patch(
        "demo.stages.retrieval_and_qa.OpenAILLM"
    ), mock.patch("neo4j.GraphDatabase.driver"), mock.patch.dict(
        os.environ, {"OPENAI_API_KEY": "test-key"}
    ), mock.patch("builtins.input", _fake_input):
        run_interactive_qa(live_config, run_id="interactive-run-cited")

    captured = capsys.readouterr()
    assert "WARNING" not in captured.out and "degraded" not in captured.out.lower()
