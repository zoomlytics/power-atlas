from __future__ import annotations

import csv
import json
import logging
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

from demo.stages import lint_and_clean_structured_csvs, run_pdf_ingest
from power_atlas.contracts import (
    Config as _RuntimeConfig,
    POWER_ATLAS_RAG_TEMPLATE,
    PROMPT_IDS,
    STRUCTURED_FILE_HEADERS,
    AmbiguousDatasetError,
    DatasetRoot,
    ALIGNMENT_VERSION,
    build_batch_manifest,
    build_stage_manifest,
    make_run_id,
    resolve_dataset_root,
)
from power_atlas.contracts.pipeline import (
    get_pipeline_contract_config_data,
    get_pipeline_contract_snapshot,
)


def Config(*args, **kwargs):
    kwargs.setdefault("pipeline_contract", get_pipeline_contract_snapshot())
    kwargs.setdefault("pipeline_contract_config_data", get_pipeline_contract_config_data())
    return _RuntimeConfig(*args, **kwargs)


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
    fixtures_dir = resolve_dataset_root("demo_dataset_v1").root
    result = lint_and_clean_structured_csvs(
        run_id="test-run",
        output_dir=tmp_path,
        fixtures_dir=fixtures_dir,
    )
    clean_dir = Path(result["structured_clean_dir"])
    assert clean_dir.exists()
    assert Path(result["lint_report_path"]).exists()
    assert result["lint_summary"]["status"] == "ok"
    lint_report = json.loads(Path(result["lint_report_path"]).read_text(encoding="utf-8"))
    assert lint_report["dataset_id"] == "demo_dataset_v1"


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
    pipeline_contract = get_pipeline_contract_snapshot()
    fixtures_dir = resolve_dataset_root("demo_dataset_v1").root
    summary = run_pdf_ingest(
        config,
        run_id="test-unstructured",
        fixtures_dir=fixtures_dir,
    )
    assert summary["vector_index"]["index_name"] == pipeline_contract.chunk_embedding_index_name
    assert summary["vector_index"]["label"] == pipeline_contract.chunk_embedding_label
    assert summary["vector_index"]["embedding_property"] == pipeline_contract.chunk_embedding_property
    assert summary["vector_index"]["dimensions"] == pipeline_contract.chunk_embedding_dimensions
    assert Path(summary["ingest_summary_path"]).exists()
    ingest_summary = json.loads(Path(summary["ingest_summary_path"]).read_text(encoding="utf-8"))
    assert ingest_summary["dataset_id"] == "demo_dataset_v1"


def test_pdf_ingest_reads_live_pipeline_contract_snapshot(tmp_path: Path):
    import demo.stages.pdf_ingest as pdf_ingest_module
    import power_atlas.contracts.pipeline as pipeline_module

    fixtures_dir = resolve_dataset_root("demo_dataset_v1").root
    original_state = pipeline_module._get_pipeline_contract_state_for_test()
    try:
        pipeline_module._set_pipeline_contract_state_for_test(
            chunk_embedding_index_name="dynamic_pdf_index"
        )
        config = _dry_run_config(tmp_path)

        summary = pdf_ingest_module.run_pdf_ingest(
            config,
            run_id="dynamic-pdf-run",
            fixtures_dir=fixtures_dir,
        )

        assert not hasattr(pdf_ingest_module, "CHUNK_EMBEDDING_INDEX_NAME")
        assert summary["vector_index"]["index_name"] == "dynamic_pdf_index"
    finally:
        pipeline_module._set_pipeline_contract_state_for_test(
            config_data=original_state.config_data,
            chunk_embedding_index_name=original_state.snapshot.chunk_embedding_index_name,
            chunk_embedding_label=original_state.snapshot.chunk_embedding_label,
            chunk_embedding_property=original_state.snapshot.chunk_embedding_property,
            chunk_embedding_dimensions=original_state.snapshot.chunk_embedding_dimensions,
            embedder_model_name=original_state.snapshot.embedder_model_name,
            chunk_fallback_stride=original_state.snapshot.chunk_fallback_stride,
        )


def test_pdf_ingest_accepts_explicit_pipeline_contract(tmp_path: Path):
    import demo.stages.pdf_ingest as pdf_ingest_module
    from power_atlas.contracts.pipeline import PipelineContractSnapshot

    config = Config(
        **{
            **_dry_run_config(tmp_path).__dict__,
            "pipeline_contract": PipelineContractSnapshot(
                chunk_embedding_index_name="explicit_pdf_index",
                chunk_embedding_label="ExplicitChunk",
                chunk_embedding_property="explicit_embedding",
                chunk_embedding_dimensions=2048,
                embedder_model_name="text-embedding-3-large",
                chunk_fallback_stride=777,
            ),
        }
    )
    fixtures_dir = resolve_dataset_root("demo_dataset_v1").root

    summary = pdf_ingest_module.run_pdf_ingest(
        config,
        run_id="explicit-pdf-run",
        fixtures_dir=fixtures_dir,
    )

    assert summary["vector_index"]["index_name"] == "explicit_pdf_index"
    assert summary["vector_index"]["label"] == "ExplicitChunk"
    assert summary["vector_index"]["embedding_property"] == "explicit_embedding"
    assert summary["vector_index"]["dimensions"] == 2048
    assert summary["embedding_model"] == "text-embedding-3-large"


def test_pdf_ingest_request_context_uses_request_scope(tmp_path: Path):
    """The RequestContext pdf-ingest helper must forward run scope and pipeline defaults."""
    import json
    from pathlib import Path

    from demo.run_demo import _request_context_from_config
    from demo.stages.pdf_ingest import run_pdf_ingest_request_context
    from power_atlas.contracts import resolve_dataset_root

    request_context = _request_context_from_config(
        _dry_run_config(tmp_path),
        command="ingest-pdf",
        run_id="context-pdf-run",
    )
    fixtures_dir = resolve_dataset_root("demo_dataset_v1").root

    summary = run_pdf_ingest_request_context(request_context, fixtures_dir=fixtures_dir)
    ingest_summary = json.loads(Path(summary["ingest_summary_path"]).read_text(encoding="utf-8"))

    assert summary["status"] == "dry_run"
    assert ingest_summary["run_id"] == "context-pdf-run"
    assert summary["vector_index"]["index_name"] == request_context.pipeline_contract.chunk_embedding_index_name


def test_structured_ingest_request_context_uses_request_scope(tmp_path: Path):
    """The RequestContext structured-ingest helper must forward run scope directly."""
    import json
    from pathlib import Path

    from demo.run_demo import _request_context_from_config
    from demo.stages.structured_ingest import run_structured_ingest_request_context
    from power_atlas.contracts import resolve_dataset_root

    request_context = _request_context_from_config(
        _dry_run_config(tmp_path),
        command="ingest-structured",
        run_id="context-structured-run",
    )
    fixtures_dir = resolve_dataset_root("demo_dataset_v1").root

    summary = run_structured_ingest_request_context(request_context, fixtures_dir=fixtures_dir)
    ingest_summary = json.loads(Path(summary["ingest_summary_path"]).read_text(encoding="utf-8"))

    assert summary["status"] == "dry_run"
    assert ingest_summary["run_id"] == "context-structured-run"
    assert summary["claims"] > 0


def test_pdf_ingest_rejects_dot_pdf_filename(tmp_path: Path):
    config = _dry_run_config(tmp_path)
    with pytest.raises(ValueError, match="pdf_filename"):
        run_pdf_ingest(config, run_id="test-unstructured", pdf_filename=".")


def test_pdf_ingest_rejects_dotdot_pdf_filename(tmp_path: Path):
    config = _dry_run_config(tmp_path)
    with pytest.raises(ValueError, match="pdf_filename"):
        run_pdf_ingest(config, run_id="test-unstructured", pdf_filename="..")


def test_pdf_ingest_rejects_traversal_pdf_filename(tmp_path: Path):
    config = _dry_run_config(tmp_path)
    with pytest.raises(ValueError, match="pdf_filename"):
        run_pdf_ingest(config, run_id="test-unstructured", pdf_filename="../../secret.pdf")


def test_pdf_ingest_rejects_non_pdf_suffix(tmp_path: Path):
    config = _dry_run_config(tmp_path)
    with pytest.raises(ValueError, match="pdf_filename"):
        run_pdf_ingest(config, run_id="test-unstructured", pdf_filename="document.txt")


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


def test_retrieval_and_qa_reads_live_pipeline_contract_snapshot(tmp_path: Path):
    import demo.stages.retrieval_and_qa as retrieval_module
    import power_atlas.contracts.pipeline as pipeline_module

    original_state = pipeline_module._get_pipeline_contract_state_for_test()
    try:
        pipeline_module._set_pipeline_contract_state_for_test(
            chunk_embedding_index_name="dynamic_retrieval_index"
        )
        config = _dry_run_config(tmp_path)

        result = retrieval_module.run_retrieval_and_qa(
            config,
            run_id="qa-dynamic-run",
            source_uri="file:///example/doc.pdf",
        )

        assert not hasattr(retrieval_module, "CHUNK_EMBEDDING_INDEX_NAME")
        assert result["retriever_index_name"] == "dynamic_retrieval_index"
    finally:
        pipeline_module._set_pipeline_contract_state_for_test(
            config_data=original_state.config_data,
            chunk_embedding_index_name=original_state.snapshot.chunk_embedding_index_name,
            chunk_embedding_label=original_state.snapshot.chunk_embedding_label,
            chunk_embedding_property=original_state.snapshot.chunk_embedding_property,
            chunk_embedding_dimensions=original_state.snapshot.chunk_embedding_dimensions,
            embedder_model_name=original_state.snapshot.embedder_model_name,
            chunk_fallback_stride=original_state.snapshot.chunk_fallback_stride,
        )


def test_retrieval_and_qa_accepts_explicit_pipeline_contract(tmp_path: Path):
    import demo.stages.retrieval_and_qa as retrieval_module
    from power_atlas.contracts.pipeline import PipelineContractSnapshot

    config = Config(
        **{
            **_dry_run_config(tmp_path).__dict__,
            "pipeline_contract": PipelineContractSnapshot(
                chunk_embedding_index_name="explicit_retrieval_index",
                chunk_embedding_label="Chunk",
                chunk_embedding_property="embedding",
                chunk_embedding_dimensions=1536,
                embedder_model_name="text-embedding-3-large",
                chunk_fallback_stride=1000,
            ),
        }
    )

    result = retrieval_module.run_retrieval_and_qa(
        config,
        run_id="qa-explicit-run",
        source_uri="file:///example/doc.pdf",
    )

    assert result["retriever_index_name"] == "explicit_retrieval_index"


def test_retrieval_and_qa_runtime_query_contract_uses_live_builder(tmp_path: Path):
    import demo.stages.retrieval_and_qa as retrieval_module

    config = _dry_run_config(tmp_path)

    with mock.patch.object(
        retrieval_module,
        "_build_retrieval_query",
        return_value="\nRETURN 'live_builder_query' AS retrieval_query\n",
    ):
        result = retrieval_module.run_retrieval_and_qa(
            config,
            run_id="qa-live-builder-run",
            expand_graph=True,
        )

    assert result["retrieval_query_contract"] == "RETURN 'live_builder_query' AS retrieval_query"


def test_retrieval_and_qa_run_id_appears_in_batch_manifest(tmp_path: Path):
    from demo.stages import run_retrieval_and_qa

    config = _dry_run_config(tmp_path)
    # Batch pipeline uses unstructured_run_id so citation examples map to stored Chunk nodes
    retrieval_stage = run_retrieval_and_qa(config, run_id="unstructured-2", source_uri=None)
    manifest = build_batch_manifest(
        config=config,
        structured_run_id="structured-1",
        unstructured_run_id="unstructured-2",
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


def test_claim_extraction_dry_run_includes_participation_edge_counts(tmp_path: Path):
    from demo.stages import run_claim_and_mention_extraction

    config = _dry_run_config(tmp_path)
    summary = run_claim_and_mention_extraction(config, run_id="claim-run-dry", source_uri=None)
    assert summary["subject_edges"] == 0
    assert summary["object_edges"] == 0


def test_claim_extraction_request_context_uses_request_scope(tmp_path: Path):
    """The RequestContext claim extraction helper must forward run and source scope directly."""
    from demo.run_demo import _request_context_from_config
    from demo.stages.claim_extraction import run_claim_and_mention_extraction_request_context

    request_context = _request_context_from_config(
        _dry_run_config(tmp_path),
        command="extract-claims",
        run_id="context-claim-run",
        source_uri="file:///context/claim.pdf",
    )

    summary = run_claim_and_mention_extraction_request_context(request_context)

    assert summary["run_id"] == "context-claim-run"
    assert summary["source_uri"] == "file:///context/claim.pdf"
    assert summary["status"] == "dry_run"


def test_entity_resolution_request_context_uses_request_scope(tmp_path: Path):
    """The RequestContext entity-resolution helper must forward run and source scope directly."""
    from demo.run_demo import _request_context_from_config
    from demo.stages.entity_resolution import run_entity_resolution_request_context

    request_context = _request_context_from_config(
        _dry_run_config(tmp_path),
        command="resolve-entities",
        run_id="context-entity-run",
        source_uri="file:///context/entity.pdf",
    )

    summary = run_entity_resolution_request_context(request_context)

    assert summary["run_id"] == "context-entity-run"
    assert summary["source_uri"] == "file:///context/entity.pdf"
    assert summary["status"] == "dry_run"


def test_claim_extraction_live_path_uses_create_lexical_graph_false(tmp_path: Path):
    """Verify that _async_read_chunks_and_extract instantiates LLMEntityRelationExtractor
    with create_lexical_graph=False, keeping extraction non-destructive:
    ingest owns lexical graph creation; extraction only adds derived outputs
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

    captured_write_all: dict = {"call_kwargs": None}

    def _fake_write_all_extraction_data(
        driver, *, neo4j_database, lexical_graph_config, claim_rows, mention_rows, edge_rows
    ):
        captured_write_all["call_kwargs"] = {
            "neo4j_database": neo4j_database,
            "claim_rows": list(claim_rows),
            "mention_rows": list(mention_rows),
            "edge_rows": list(edge_rows),
        }

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
        "demo.extraction_utils.write_all_extraction_data",
        side_effect=_fake_write_all_extraction_data,
    ), mock.patch("neo4j.GraphDatabase.driver"), mock.patch.dict(os.environ, {"OPENAI_API_KEY": "test-key"}):
        summary = run_claim_and_mention_extraction(config, run_id="live-run", source_uri="file:///doc.pdf")

    # Core assertion: the extractor must be built with create_lexical_graph=False
    assert extractor_init_kwargs.get("create_lexical_graph") is False

    assert summary["status"] == "live"
    assert summary["run_id"] == "live-run"
    assert summary["claims"] == 1
    assert summary["mentions"] == 1

    # write_all_extraction_data must have been called with all row data.
    assert captured_write_all["call_kwargs"] is not None, "write_all_extraction_data was never called"
    kw = captured_write_all["call_kwargs"]

    # Verify chunk-linked provenance: every extracted row must reference the source chunk_id
    assert kw["claim_rows"][0]["chunk_ids"] == [chunk_id]
    assert kw["mention_rows"][0]["chunk_ids"] == [chunk_id]
    assert kw["claim_rows"][0]["run_id"] == "live-run"
    assert kw["mention_rows"][0]["run_id"] == "live-run"

    # Verify participation edge counts in the summary.
    # The claim subject is "s" and the mention name is "Live Entity" — no raw match,
    # so no edges are expected; but write_all_extraction_data must still have been invoked.
    assert summary["subject_edges"] == 0
    assert summary["object_edges"] == 0


def test_claim_extraction_live_writes_participation_edges_when_mention_matches(tmp_path: Path):
    """Participation edges must be written inline when claim slot text matches a mention name."""
    from demo.stages import run_claim_and_mention_extraction

    chunk_id = "chunk-match-1"
    # Claim subject matches the mention name exactly.
    fake_graph = Neo4jGraph(
        nodes=[
            Neo4jNode(
                id="claim-match-1",
                label="ExtractedClaim",
                properties={"claim_text": "Google earns revenue", "subject": "Google", "object": "revenue"},
            ),
            Neo4jNode(
                id="mention-match-google",
                label="EntityMention",
                properties={"name": "Google", "entity_type": "ORG"},
            ),
            Neo4jNode(
                id="mention-match-revenue",
                label="EntityMention",
                properties={"name": "revenue", "entity_type": "CONCEPT"},
            ),
        ],
        relationships=[
            Neo4jRelationship(start_node_id=chunk_id, end_node_id="claim-match-1", type="MENTIONED_IN"),
            Neo4jRelationship(start_node_id=chunk_id, end_node_id="mention-match-google", type="MENTIONED_IN"),
            Neo4jRelationship(start_node_id=chunk_id, end_node_id="mention-match-revenue", type="MENTIONED_IN"),
        ],
    )
    fake_chunks = TextChunks(
        chunks=[TextChunk(uid=chunk_id, text="Google earns revenue", index=0, metadata={"run_id": "match-run"})]
    )

    class _FakeExtractor:
        def __init__(self, **kwargs):
            pass

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

    captured_write_all: dict = {"call_kwargs": None}

    def _fake_write_all_extraction_data(
        driver, *, neo4j_database, lexical_graph_config, claim_rows, mention_rows, edge_rows
    ):
        captured_write_all["call_kwargs"] = {
            "edge_rows": list(edge_rows),
        }

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
        "demo.extraction_utils.write_all_extraction_data",
        side_effect=_fake_write_all_extraction_data,
    ), mock.patch("neo4j.GraphDatabase.driver"), mock.patch.dict(os.environ, {"OPENAI_API_KEY": "test-key"}):
        summary = run_claim_and_mention_extraction(config, run_id="match-run", source_uri="file:///doc.pdf")

    # write_all_extraction_data must have been called.
    assert captured_write_all["call_kwargs"] is not None, "write_all_extraction_data was never called"

    # Both subject ("Google") and object ("revenue") should have matched a mention.
    assert summary["subject_edges"] == 1
    assert summary["object_edges"] == 1

    edge_rows = captured_write_all["call_kwargs"]["edge_rows"]
    assert summary["subject_edges"] + summary["object_edges"] == len(edge_rows)

    edge_types = {e["edge_type"] for e in edge_rows}
    assert "HAS_PARTICIPANT" in edge_types
    roles = {e["role"] for e in edge_rows}
    assert "subject" in roles
    assert "object" in roles

    # Each edge must record run_id and match_method provenance.
    from demo.stages.claim_participation import (
        MATCH_METHOD_CASEFOLD_EXACT,
        MATCH_METHOD_LIST_SPLIT,
        MATCH_METHOD_NORMALIZED_EXACT,
        MATCH_METHOD_RAW_EXACT,
    )
    for edge in edge_rows:
        assert edge["run_id"] == "match-run"
        assert edge["match_method"] in (
            MATCH_METHOD_RAW_EXACT,
            MATCH_METHOD_CASEFOLD_EXACT,
            MATCH_METHOD_NORMALIZED_EXACT,
            MATCH_METHOD_LIST_SPLIT,
        )


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


def _make_fake_neo4j_record(**kwargs) -> "dict[str, object]":
    """Build a minimal dict-based fake neo4j.Record for use with _chunk_citation_formatter.

    neo4j.Record supports dict-style .get() so a plain subclass with a forwarding
    ``get`` is sufficient; no actual Neo4j connection is needed.
    """

    class _FakeRecord(dict):
        def get(self, key, default=None):
            return super().get(key, default)

    return _FakeRecord(**kwargs)


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

    captured_init: dict = {}
    captured_search: dict = {}
    captured_embedder_args: list = []
    pipeline_contract = get_pipeline_contract_snapshot()

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
        "demo.stages.retrieval_and_qa.build_openai_llm"
    ), mock.patch("neo4j.GraphDatabase.driver"), mock.patch.dict(os.environ, {"OPENAI_API_KEY": "test-key"}):
        result = run_retrieval_and_qa(
            live_config,
            run_id="live-run-1",
            source_uri="file:///doc.pdf",
            top_k=3,
            question="What happened?",
        )

    assert captured_init["index_name"] == pipeline_contract.chunk_embedding_index_name
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
    assert captured_embedder_args[0][1].get("model") == pipeline_contract.embedder_model_name


def test_retrieval_and_qa_live_path_uses_explicit_pipeline_contract(tmp_path: Path):
    from demo.stages import run_retrieval_and_qa
    from demo.stages.retrieval_and_qa import _chunk_citation_formatter
    from power_atlas.contracts.pipeline import PipelineContractSnapshot

    captured_init: dict = {}
    captured_embedder_args: list = []

    class _FakeEmbedder:
        def __init__(self, *args, **kwargs):
            captured_embedder_args.append((args, kwargs))

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

    explicit_pipeline_contract = PipelineContractSnapshot(
        chunk_embedding_index_name="explicit_live_retrieval_index",
        chunk_embedding_label="Chunk",
        chunk_embedding_property="embedding",
        chunk_embedding_dimensions=1536,
        embedder_model_name="text-embedding-3-large",
        chunk_fallback_stride=1000,
    )

    _StubGraphRAG = _make_stub_graphrag_class()

    with mock.patch("demo.stages.retrieval_and_qa.VectorCypherRetriever", _FakeRetriever), mock.patch(
        "demo.stages.retrieval_and_qa.OpenAIEmbeddings", _FakeEmbedder
    ), mock.patch("demo.stages.retrieval_and_qa.GraphRAG", _StubGraphRAG), mock.patch(
        "demo.stages.retrieval_and_qa.build_openai_llm"
    ), mock.patch("neo4j.GraphDatabase.driver"), mock.patch.dict(os.environ, {"OPENAI_API_KEY": "test-key"}):
        live_config = Config(**{**live_config.__dict__, "pipeline_contract": explicit_pipeline_contract})
        result = run_retrieval_and_qa(
            live_config,
            run_id="live-run-explicit",
            source_uri="file:///doc.pdf",
            top_k=3,
            question="What happened?",
        )

    assert captured_init["index_name"] == "explicit_live_retrieval_index"
    assert captured_init["result_formatter"] is _chunk_citation_formatter
    assert result["status"] == "live"
    assert len(captured_embedder_args) == 1
    assert captured_embedder_args[0][1].get("model") == "text-embedding-3-large"


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
        "demo.stages.retrieval_and_qa.build_openai_llm"
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
        "demo.stages.retrieval_and_qa.build_openai_llm"
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
        "demo.stages.retrieval_and_qa.build_openai_llm"
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
        "demo.stages.retrieval_and_qa.build_openai_llm"
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


def test_retrieval_and_qa_dry_run_cluster_aware_flag_recorded(tmp_path: Path):
    """cluster_aware flag must be preserved in the returned stage output and the
    retrievers list must include 'cluster traversal' when cluster_aware=True.
    expand_graph must be True when cluster_aware=True (cluster_aware implies expansion)."""
    from demo.stages import run_retrieval_and_qa

    config = _dry_run_config(tmp_path)
    result_no_cluster = run_retrieval_and_qa(config, run_id="qa-run-ca-1", source_uri=None, cluster_aware=False)
    result_cluster = run_retrieval_and_qa(config, run_id="qa-run-ca-2", source_uri=None, cluster_aware=True)
    assert result_no_cluster["cluster_aware"] is False
    assert result_cluster["cluster_aware"] is True
    # retrievers list must include "cluster traversal" only when cluster_aware=True
    assert "cluster traversal" not in result_no_cluster["retrievers"]
    assert "cluster traversal" in result_cluster["retrievers"]
    # cluster_aware implies graph expansion — both labels and expand_graph flag should reflect that
    assert "graph expansion" in result_cluster["retrievers"]
    assert result_cluster["expand_graph"] is True


def test_retrieval_and_qa_live_path_uses_cluster_query_when_cluster_aware(tmp_path: Path):
    """When cluster_aware=True, the retriever must be initialised with the cluster-aware query."""
    from demo.stages import run_retrieval_and_qa
    from demo.stages.retrieval_and_qa import _RETRIEVAL_QUERY_WITH_CLUSTER

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
        "demo.stages.retrieval_and_qa.build_openai_llm"
    ), mock.patch("neo4j.GraphDatabase.driver"), mock.patch.dict(os.environ, {"OPENAI_API_KEY": "test-key"}):
        result = run_retrieval_and_qa(
            live_config,
            run_id="cluster-run",
            source_uri=None,
            question="Test cluster",
            cluster_aware=True,
        )

    assert captured_init["retrieval_query"] == _RETRIEVAL_QUERY_WITH_CLUSTER
    assert result["cluster_aware"] is True
    assert "cluster traversal" in result["retrievers"]
    assert "graph expansion" in result["retrievers"]
    # expand_graph must be True when cluster_aware=True (cluster_aware implies expansion)
    assert result["expand_graph"] is True


def test_retrieval_and_qa_live_path_cluster_aware_all_runs_uses_all_runs_query(tmp_path: Path):
    """When cluster_aware=True and all_runs=True, the all-runs cluster query must be used."""
    from demo.stages import run_retrieval_and_qa
    from demo.stages.retrieval_and_qa import _RETRIEVAL_QUERY_WITH_CLUSTER_ALL_RUNS

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
        "demo.stages.retrieval_and_qa.build_openai_llm"
    ), mock.patch("neo4j.GraphDatabase.driver"), mock.patch.dict(os.environ, {"OPENAI_API_KEY": "test-key"}):
        result = run_retrieval_and_qa(
            live_config,
            run_id=None,
            source_uri=None,
            question="Test cluster all runs",
            cluster_aware=True,
            all_runs=True,
        )

    assert captured_init["retrieval_query"] == _RETRIEVAL_QUERY_WITH_CLUSTER_ALL_RUNS
    assert result["cluster_aware"] is True


def test_format_cluster_context_provisional_membership():
    """_format_cluster_context must label provisional memberships as PROVISIONAL CLUSTER."""
    from demo.stages.retrieval_and_qa import _format_cluster_context

    memberships = [
        {"cluster_name": "John Smith", "membership_status": "provisional", "membership_method": "fuzzy"},
    ]
    result = _format_cluster_context(memberships, [])
    assert "PROVISIONAL CLUSTER" in result
    assert "John Smith" in result
    assert "fuzzy" in result
    assert "not confirmed" in result.lower() or "hypothesis" in result.lower()


def test_format_cluster_context_accepted_membership():
    """_format_cluster_context must label accepted memberships with 'Entity cluster (accepted)'."""
    from demo.stages.retrieval_and_qa import _format_cluster_context

    memberships = [
        {"cluster_name": "Jane Doe", "membership_status": "accepted", "membership_method": "label_cluster"},
    ]
    result = _format_cluster_context(memberships, [])
    assert "PROVISIONAL CLUSTER" not in result
    assert "REVIEW REQUIRED CLUSTER" not in result
    assert "CANDIDATE CLUSTER" not in result
    assert "Jane Doe" in result
    assert "Entity cluster (accepted)" in result


def test_format_cluster_context_candidate_membership():
    """_format_cluster_context must label candidate memberships with 'CANDIDATE CLUSTER'."""
    from demo.stages.retrieval_and_qa import _format_cluster_context

    memberships = [
        {"cluster_name": "FBI", "membership_status": "candidate", "membership_method": "abbreviation"},
    ]
    result = _format_cluster_context(memberships, [])
    assert "CANDIDATE CLUSTER" in result
    assert "FBI" in result
    assert "REVIEW REQUIRED CLUSTER" not in result
    assert "PROVISIONAL CLUSTER" not in result
    assert "Entity cluster (accepted)" not in result
    assert "abbreviated form" in result.lower() or "candidate" in result.lower()


def test_format_cluster_context_review_required_membership():
    """_format_cluster_context must label review_required memberships with 'REVIEW REQUIRED CLUSTER'."""
    from demo.stages.retrieval_and_qa import _format_cluster_context

    memberships = [
        {"cluster_name": "Euro Central Bank", "membership_status": "review_required", "membership_method": "fuzzy"},
    ]
    result = _format_cluster_context(memberships, [])
    assert "REVIEW REQUIRED CLUSTER" in result
    assert "Euro Central Bank" in result
    assert "CANDIDATE CLUSTER" not in result
    assert "PROVISIONAL CLUSTER" not in result
    assert "Entity cluster (accepted)" not in result
    assert "review" in result.lower()


def test_format_cluster_context_provisional_alignment():
    """_format_cluster_context must label non-aligned canonical alignments as PROVISIONAL ALIGNMENT."""
    from demo.stages.retrieval_and_qa import _format_cluster_context

    alignments = [
        {"canonical_name": "John Smith (Wikidata)", "alignment_method": "alias_exact", "alignment_status": "tentative"},
    ]
    result = _format_cluster_context([], alignments)
    assert "PROVISIONAL ALIGNMENT" in result
    assert "John Smith (Wikidata)" in result
    assert "not yet confirmed" in result.lower() or "tentative" in result.lower()


def test_format_cluster_context_confirmed_alignment():
    """_format_cluster_context must use the 'aligned' label for confirmed canonical alignments."""
    from demo.stages.retrieval_and_qa import _format_cluster_context

    alignments = [
        {"canonical_name": "Jane Doe (Canon)", "alignment_method": "label_exact", "alignment_status": "aligned"},
    ]
    result = _format_cluster_context([], alignments)
    assert "PROVISIONAL ALIGNMENT" not in result
    assert "Jane Doe (Canon)" in result
    assert "aligned" in result.lower() or "canonical entity" in result.lower()


def test_format_cluster_context_empty_inputs():
    """_format_cluster_context must return empty string when both inputs are empty."""
    from demo.stages.retrieval_and_qa import _format_cluster_context

    assert _format_cluster_context([], []) == ""


def test_chunk_citation_formatter_includes_cluster_context_in_content():
    """_chunk_citation_formatter must include cluster context in content when cluster fields
    are present in the record, and the context must be labelled as provisional inference."""
    from demo.stages.retrieval_and_qa import _chunk_citation_formatter

    record = _make_fake_neo4j_record(
        chunk_id="c1",
        run_id="r1",
        source_uri="file:///doc.pdf",
        chunk_index=0,
        page=1,
        start_char=0,
        end_char=100,
        chunk_text="Some evidence text.",
        similarityScore=0.9,
        cluster_memberships=[
            {"cluster_name": "J. Smith", "membership_status": "provisional", "membership_method": "fuzzy"},
        ],
        cluster_canonical_alignments=[],
    )
    item = _chunk_citation_formatter(record)
    assert "Some evidence text." in item.content
    assert "PROVISIONAL CLUSTER" in item.content
    assert "J. Smith" in item.content
    assert "[Cluster context" in item.content
    # Citation token must still be present
    assert "[CITATION|" in item.content
    # Cluster fields must also appear in metadata
    assert item.metadata["cluster_memberships"] is not None


def test_chunk_citation_formatter_no_cluster_context_when_fields_absent():
    """_chunk_citation_formatter must not include cluster context section when cluster
    fields are absent from the record (non-cluster-aware query)."""
    from demo.stages.retrieval_and_qa import _chunk_citation_formatter

    record = _make_fake_neo4j_record(
        chunk_id="c2",
        run_id="r1",
        source_uri="file:///doc.pdf",
        chunk_index=1,
        page=2,
        start_char=100,
        end_char=200,
        chunk_text="Another evidence text.",
        similarityScore=0.85,
        # No cluster_memberships or cluster_canonical_alignments keys
    )
    item = _chunk_citation_formatter(record)
    assert "Another evidence text." in item.content
    assert "[Cluster context" not in item.content
    assert "PROVISIONAL" not in item.content
    assert "[CITATION|" in item.content


def test_chunk_citation_formatter_no_cluster_context_when_fields_empty():
    """_chunk_citation_formatter must not include cluster context section when cluster
    lists are empty (cluster-aware query but no clusters found for this chunk)."""
    from demo.stages.retrieval_and_qa import _chunk_citation_formatter

    record = _make_fake_neo4j_record(
        chunk_id="c3",
        run_id="r1",
        source_uri="file:///doc.pdf",
        chunk_index=2,
        page=3,
        start_char=200,
        end_char=300,
        chunk_text="Third evidence text.",
        similarityScore=0.80,
        cluster_memberships=[],
        cluster_canonical_alignments=[],
    )
    item = _chunk_citation_formatter(record)
    assert "[Cluster context" not in item.content
    assert "PROVISIONAL" not in item.content


def test_retrieval_and_qa_cluster_aware_retrieval_query_contract_recorded(tmp_path: Path):
    """The retrieval_query_contract in the result must use the cluster-aware query when
    cluster_aware=True, so manifests accurately document which retrieval strategy was used."""
    from demo.stages import run_retrieval_and_qa
    from demo.stages.retrieval_and_qa import _RETRIEVAL_QUERY_WITH_CLUSTER

    config = _dry_run_config(tmp_path)
    result = run_retrieval_and_qa(config, run_id="qa-run-ca-3", source_uri=None, cluster_aware=True)
    assert result["retrieval_query_contract"] == _RETRIEVAL_QUERY_WITH_CLUSTER.strip()


def test_retrieval_and_qa_cluster_aware_passes_alignment_version_in_query_params(tmp_path: Path):
    """When cluster_aware=True, alignment_version must be included in the query params passed to
    the retriever so that ALIGNED_WITH edge filtering in the Cypher query is version-scoped."""
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
        "demo.stages.retrieval_and_qa.build_openai_llm"
    ), mock.patch("neo4j.GraphDatabase.driver"), mock.patch.dict(os.environ, {"OPENAI_API_KEY": "test-key"}):
        run_retrieval_and_qa(
            live_config,
            run_id="cluster-av-run",
            source_uri=None,
            question="Test alignment version?",
            cluster_aware=True,
        )

    assert "alignment_version" in captured_params, (
        "cluster_aware retrieval must pass alignment_version in query_params for ALIGNED_WITH filtering"
    )
    assert captured_params["alignment_version"] == ALIGNMENT_VERSION


def test_retrieval_and_qa_cluster_aware_query_params_omit_alignment_version_when_not_cluster_aware(tmp_path: Path):
    """alignment_version must NOT appear in query params when cluster_aware=False, because the
    non-cluster queries do not use ALIGNED_WITH edges and the param would be unexpected noise."""
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
        "demo.stages.retrieval_and_qa.build_openai_llm"
    ), mock.patch("neo4j.GraphDatabase.driver"), mock.patch.dict(os.environ, {"OPENAI_API_KEY": "test-key"}):
        run_retrieval_and_qa(
            live_config,
            run_id="no-cluster-run",
            source_uri=None,
            question="Test non-cluster?",
            cluster_aware=False,
        )

    assert "alignment_version" not in captured_params, (
        "non-cluster-aware retrieval must not pass alignment_version in query_params"
    )


def test_retrieval_and_qa_cluster_aware_live_path_surfaces_member_of_traversal(tmp_path: Path):
    """Live cluster-aware retrieval must surface cluster_memberships (MEMBER_OF traversal) in
    retrieval_results metadata, verifying that indirect mention→cluster expansion reaches the
    result layer so downstream consumers can inspect the traversal path."""
    from demo.stages import run_retrieval_and_qa
    from demo.stages.retrieval_and_qa import _chunk_citation_formatter

    cluster_membership_data = [
        {
            "cluster_id": "cluster::run1::PERSON::john%20smith",
            "cluster_name": "John Smith",
            "membership_status": "provisional",
            "membership_method": "fuzzy",
        }
    ]
    record = _make_fake_neo4j_record(
        chunk_id="chunk-cluster-1",
        run_id="cluster-live-run",
        source_uri="file:///evidence.pdf",
        chunk_index=0,
        page=1,
        start_char=0,
        end_char=150,
        chunk_text="John Smith was involved in the transaction.",
        similarityScore=0.92,
        mentions=["John Smith"],
        claims=[],
        canonical_entities=[],
        cluster_memberships=cluster_membership_data,
        cluster_canonical_alignments=[],
    )
    item = _chunk_citation_formatter(record)

    class _FakeRetriever:
        def __init__(self, **kwargs):
            pass

        def search(self, **kwargs):
            return _make_fake_retriever_result([item])

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
        "demo.stages.retrieval_and_qa.build_openai_llm"
    ), mock.patch("neo4j.GraphDatabase.driver"), mock.patch.dict(os.environ, {"OPENAI_API_KEY": "test-key"}):
        result = run_retrieval_and_qa(
            live_config,
            run_id="cluster-live-run",
            source_uri=None,
            question="Who was involved?",
            cluster_aware=True,
        )

    assert result["status"] == "live"
    assert result["hits"] == 1
    assert len(result["retrieval_results"]) == 1

    # The retrieval result must expose cluster_memberships so the traversal path is visible
    hit_meta = result["retrieval_results"][0]["metadata"]
    assert "cluster_memberships" in hit_meta, (
        "cluster-aware retrieval results must include cluster_memberships in metadata"
    )
    assert hit_meta["cluster_memberships"] == cluster_membership_data, (
        "cluster_memberships in result metadata must match the MEMBER_OF traversal data"
    )

    # The content string must include the cluster context label
    hit_content = result["retrieval_results"][0]["content"]
    assert "PROVISIONAL CLUSTER" in hit_content, (
        "retrieval result content must include PROVISIONAL CLUSTER label from MEMBER_OF traversal"
    )
    assert "John Smith" in hit_content


def test_retrieval_and_qa_cluster_aware_live_path_surfaces_aligned_with_traversal(tmp_path: Path):
    """Live cluster-aware retrieval must surface cluster_canonical_alignments (ALIGNED_WITH
    traversal via cluster node) in retrieval_results metadata.  This verifies that the indirect
    path mention→MEMBER_OF→cluster→ALIGNED_WITH→canonical actually reaches the result layer."""
    from demo.stages import run_retrieval_and_qa
    from demo.stages.retrieval_and_qa import _chunk_citation_formatter

    cluster_canonical_alignment_data = [
        {
            "canonical_name": "John Smith (Q12345)",
            "alignment_method": "label_exact",
            "alignment_status": "aligned",
        }
    ]
    record = _make_fake_neo4j_record(
        chunk_id="chunk-aligned-1",
        run_id="aligned-live-run",
        source_uri="file:///evidence.pdf",
        chunk_index=1,
        page=2,
        start_char=150,
        end_char=300,
        chunk_text="The suspect matched the canonical entity.",
        similarityScore=0.88,
        mentions=["John Smith"],
        claims=[],
        canonical_entities=[],
        cluster_memberships=[
            {
                "cluster_id": "cluster::run1::PERSON::john%20smith",
                "cluster_name": "John Smith",
                "membership_status": "accepted",
                "membership_method": "label_cluster",
            }
        ],
        cluster_canonical_alignments=cluster_canonical_alignment_data,
    )
    item = _chunk_citation_formatter(record)

    class _FakeRetriever:
        def __init__(self, **kwargs):
            pass

        def search(self, **kwargs):
            return _make_fake_retriever_result([item])

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
        "demo.stages.retrieval_and_qa.build_openai_llm"
    ), mock.patch("neo4j.GraphDatabase.driver"), mock.patch.dict(os.environ, {"OPENAI_API_KEY": "test-key"}):
        result = run_retrieval_and_qa(
            live_config,
            run_id="aligned-live-run",
            source_uri=None,
            question="Who is the canonical entity?",
            cluster_aware=True,
        )

    assert result["status"] == "live"
    assert result["hits"] == 1

    hit_meta = result["retrieval_results"][0]["metadata"]

    # cluster_canonical_alignments must be present: this is the ALIGNED_WITH traversal path
    assert "cluster_canonical_alignments" in hit_meta, (
        "cluster-aware retrieval results must include cluster_canonical_alignments from ALIGNED_WITH traversal"
    )
    assert hit_meta["cluster_canonical_alignments"] == cluster_canonical_alignment_data

    # The content must carry the canonical alignment label
    hit_content = result["retrieval_results"][0]["content"]
    assert "John Smith (Q12345)" in hit_content, (
        "canonical entity name reached via ALIGNED_WITH must appear in retrieval result content"
    )
    assert "Cluster aligned to canonical entity" in hit_content, (
        "confirmed ALIGNED_WITH traversal must render as 'Cluster aligned to canonical entity'"
    )


def test_retrieval_and_qa_cluster_aware_hybrid_traversal_both_member_of_and_aligned_with(tmp_path: Path):
    """Full hybrid traversal test: a single retrieved chunk whose mentions reach a
    ResolvedEntityCluster (via MEMBER_OF) which is itself aligned to a CanonicalEntity
    (via ALIGNED_WITH).  Both cluster_memberships and cluster_canonical_alignments must
    appear in the retrieval result, confirming the complete indirect expansion path."""
    from demo.stages import run_retrieval_and_qa
    from demo.stages.retrieval_and_qa import _chunk_citation_formatter

    membership_data = [
        {
            "cluster_id": "cluster::hybrid-run::ORG::acme%20corp",
            "cluster_name": "Acme Corp",
            "membership_status": "provisional",
            "membership_method": "fuzzy",
        }
    ]
    alignment_data = [
        {
            "canonical_name": "Acme Corporation (Wikidata Q99)",
            "alignment_method": "alias_exact",
            "alignment_status": "tentative",
        }
    ]
    record = _make_fake_neo4j_record(
        chunk_id="chunk-hybrid-1",
        run_id="hybrid-run",
        source_uri="file:///report.pdf",
        chunk_index=0,
        page=5,
        start_char=200,
        end_char=400,
        chunk_text="Acme Corp signed a contract with the government.",
        similarityScore=0.91,
        mentions=["Acme Corp"],
        claims=["Acme Corp signed a contract."],
        canonical_entities=[],
        cluster_memberships=membership_data,
        cluster_canonical_alignments=alignment_data,
    )
    item = _chunk_citation_formatter(record)

    class _FakeRetriever:
        def __init__(self, **kwargs):
            pass

        def search(self, **kwargs):
            return _make_fake_retriever_result([item])

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
        "demo.stages.retrieval_and_qa.build_openai_llm"
    ), mock.patch("neo4j.GraphDatabase.driver"), mock.patch.dict(os.environ, {"OPENAI_API_KEY": "test-key"}):
        result = run_retrieval_and_qa(
            live_config,
            run_id="hybrid-run",
            source_uri=None,
            question="What did Acme Corp sign?",
            cluster_aware=True,
        )

    assert result["status"] == "live"
    assert result["hits"] == 1

    hit_meta = result["retrieval_results"][0]["metadata"]

    # Both traversal paths must surface in metadata
    assert hit_meta["cluster_memberships"] == membership_data, (
        "MEMBER_OF traversal data must appear in retrieval result metadata"
    )
    assert hit_meta["cluster_canonical_alignments"] == alignment_data, (
        "ALIGNED_WITH traversal data must appear in retrieval result metadata"
    )

    # Content must include both cluster context labels
    hit_content = result["retrieval_results"][0]["content"]
    assert "PROVISIONAL CLUSTER" in hit_content, "provisional MEMBER_OF membership must label content"
    assert "Acme Corp" in hit_content
    assert "PROVISIONAL ALIGNMENT" in hit_content, "tentative ALIGNED_WITH edge must label content as provisional"
    assert "Acme Corporation (Wikidata Q99)" in hit_content


def test_format_cluster_context_deduplicates_repeated_memberships():
    """_format_cluster_context must collapse duplicate (cluster_name, method, status) entries
    that arise when multiple EntityMention nodes in the same chunk point at the same cluster."""
    from demo.stages.retrieval_and_qa import _format_cluster_context

    # Two memberships with identical cluster_name/method/status — typical when two
    # co-reference mentions in the same chunk both have MEMBER_OF edges to the same cluster.
    memberships = [
        {"cluster_name": "Apple Inc", "membership_status": "accepted", "membership_method": "label_cluster"},
        {"cluster_name": "Apple Inc", "membership_status": "accepted", "membership_method": "label_cluster"},
        {"cluster_name": "Apple Inc", "membership_status": "accepted", "membership_method": "label_cluster"},
    ]
    result = _format_cluster_context(memberships, [])
    # The cluster name should appear exactly once despite three identical entries
    assert result.count("Apple Inc") == 1, (
        "_format_cluster_context must deduplicate identical cluster membership entries"
    )


def test_format_cluster_context_deduplicates_repeated_alignments():
    """_format_cluster_context must deduplicate repeated canonical alignment entries that
    arise when the same ALIGNED_WITH edge is traversed from multiple mention paths."""
    from demo.stages.retrieval_and_qa import _format_cluster_context

    alignments = [
        {"canonical_name": "Apple Inc. (Q312)", "alignment_method": "label_exact", "alignment_status": "aligned"},
        {"canonical_name": "Apple Inc. (Q312)", "alignment_method": "label_exact", "alignment_status": "aligned"},
    ]
    result = _format_cluster_context([], alignments)
    assert result.count("Apple Inc. (Q312)") == 1, (
        "_format_cluster_context must deduplicate identical canonical alignment entries"
    )


def test_format_cluster_context_falls_back_to_cluster_id_when_name_absent():
    """_format_cluster_context must use cluster_id as the display label when cluster_name is
    absent or empty, so the cluster context section is always informative even for clusters
    whose canonical_name has not yet been set."""
    from demo.stages.retrieval_and_qa import _format_cluster_context

    memberships = [
        {
            "cluster_id": "cluster::run1::PERSON::jane%20doe",
            "cluster_name": None,
            "membership_status": "provisional",
            "membership_method": "fuzzy",
        }
    ]
    result = _format_cluster_context(memberships, [])
    assert "cluster::run1::PERSON::jane%20doe" in result, (
        "_format_cluster_context must fall back to cluster_id when cluster_name is absent"
    )
    assert "PROVISIONAL CLUSTER" in result


def test_format_cluster_context_handles_unknown_membership_status():
    """_format_cluster_context must handle membership statuses outside the known set
    by falling back to the PROVISIONAL CLUSTER label with the raw status preserved,
    so novel pipeline statuses do not raise errors or silently discard information."""
    from demo.stages.retrieval_and_qa import _format_cluster_context

    memberships = [
        {
            "cluster_name": "Some Entity",
            "membership_status": "experimental_new_status",
            "membership_method": "ml_classifier",
        }
    ]
    result = _format_cluster_context(memberships, [])
    assert "PROVISIONAL CLUSTER" in result, (
        "unknown membership status must fall back to PROVISIONAL CLUSTER label"
    )
    assert "Some Entity" in result
    assert "experimental_new_status" in result, (
        "unknown status value must be preserved in the rendered output for traceability"
    )


def test_power_atlas_rag_template_includes_provisional_cluster_instructions():
    """The prompt template must include instructions for handling provisional cluster context."""
    tmpl = POWER_ATLAS_RAG_TEMPLATE.template
    sys_instructions = POWER_ATLAS_RAG_TEMPLATE.system_instructions

    assert "provisional" in tmpl.lower(), (
        "Template must mention provisional cluster handling"
    )
    assert "PROVISIONAL CLUSTER" in tmpl or "provisional cluster" in tmpl.lower(), (
        "Template must reference provisional cluster labels"
    )
    assert "settled identity" in tmpl.lower() or "settled" in tmpl.lower(), (
        "Template must prohibit presenting provisional inferences as settled identity claims"
    )
    # System instructions must also carry the provisional cluster posture
    assert "provisional" in sys_instructions.lower(), (
        "System instructions must reference provisional cluster handling"
    )


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
    tmpl = POWER_ATLAS_RAG_TEMPLATE.template
    assert "[CITATION|" in tmpl, "Template must reference citation token format"
    assert "context" in tmpl.lower(), "Template must reference context"
    assert "insuffic" in tmpl.lower() or "insufficient" in tmpl.lower(), (
        "Template must mention insufficient context handling"
    )
    assert "conflict" in tmpl.lower(), "Template must mention conflicting evidence handling"


def test_power_atlas_rag_template_prohibits_history_as_evidence():
    """The Power Atlas RagTemplate must explicitly state that message history provides
    conversational context only and must never be used as answer evidence."""
    tmpl = POWER_ATLAS_RAG_TEMPLATE.template
    sys_instructions = POWER_ATLAS_RAG_TEMPLATE.system_instructions

    # The template body must contain the exact phrase added for this constraint.
    assert "Message history (prior conversation turns) provides conversational context ONLY" in tmpl, (
        "Template body must contain the explicit message-history-context-only rule"
    )
    assert "Do NOT cite or treat any prior assistant turn as evidence" in tmpl, (
        "Template body must explicitly prohibit treating prior assistant turns as evidence"
    )

    # The system instructions must also carry the exact phrases added for this constraint.
    assert "Message history provides conversational context only, never evidence" in sys_instructions, (
        "System instructions must state that message history is context-only, never evidence"
    )
    assert "Do not source any answer evidence from prior assistant turns" in sys_instructions, (
        "System instructions must explicitly prohibit sourcing evidence from prior assistant turns"
    )


def test_power_atlas_rag_template_uses_vendor_rag_template_class():
    """Power Atlas template must extend the vendor RagTemplate for GraphRAG wiring."""
    from neo4j_graphrag.generation import RagTemplate

    assert isinstance(POWER_ATLAS_RAG_TEMPLATE, RagTemplate)


def test_power_atlas_rag_template_prompt_id_updated():
    """qa prompt ID must reflect the updated prompt version (qa_v3) with cluster-aware instructions."""
    assert PROMPT_IDS["qa"] == "qa_v3", (
        "PROMPT_IDS['qa'] must be updated to 'qa_v3' to reflect the cluster-aware prompt template"
    )


def test_demo_prompt_contract_shim_matches_package_exports():
    from demo.contracts.prompts import POWER_ATLAS_RAG_TEMPLATE as demo_prompt_template
    from demo.contracts.prompts import PROMPT_IDS as demo_prompt_ids

    assert demo_prompt_template is POWER_ATLAS_RAG_TEMPLATE
    assert demo_prompt_ids is PROMPT_IDS


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


def test_check_all_answers_cited_rejects_multi_sentence_line_only_last_cited():
    """_check_all_answers_cited must return False when a single line contains multiple
    sentences but only the last sentence ends with a citation token.

    This is the key sentence-level check: 'A. B. [CITATION]' must be rejected because
    sentence 'A.' does not itself end with a citation token.
    """
    from demo.stages.retrieval_and_qa import _check_all_answers_cited

    # Two sentences on one line; only the second ends with a citation.
    answer = (
        "The audit was completed in 2022. The findings were inconclusive. "
        "[CITATION|chunk_id=c1|run_id=r1|source_uri=file:///x.pdf|chunk_index=0|page=1|start_char=0|end_char=80]"
    )
    assert _check_all_answers_cited(answer) is False


def test_check_all_answers_cited_accepts_multi_sentence_line_each_cited():
    """_check_all_answers_cited must return True when a single line contains multiple
    sentences and each sentence ends with its own citation token.
    """
    from demo.stages.retrieval_and_qa import _check_all_answers_cited

    # Two sentences on one line; each ends with its own citation token.
    answer = (
        "The audit was completed in 2022. "
        "[CITATION|chunk_id=c1|run_id=r1|source_uri=file:///x.pdf|chunk_index=0|page=1|start_char=0|end_char=40] "
        "The findings were inconclusive. "
        "[CITATION|chunk_id=c2|run_id=r1|source_uri=file:///x.pdf|chunk_index=1|page=1|start_char=41|end_char=80]"
    )
    assert _check_all_answers_cited(answer) is True


def test_split_into_segments_newline_splitting():
    """_split_into_segments must split on newlines and return one segment per non-empty line
    when lines are simple single-sentence paragraphs."""
    from demo.stages.retrieval_and_qa import _split_into_segments

    answer = "First sentence. [CITATION|chunk_id=c1|run_id=r1|source_uri=s|chunk_index=0|page=1|start_char=0|end_char=10]\nSecond sentence. [CITATION|chunk_id=c2|run_id=r1|source_uri=s|chunk_index=1|page=1|start_char=11|end_char=20]"
    segments = _split_into_segments(answer)
    assert len(segments) == 2
    assert segments[0] == "First sentence. [CITATION|chunk_id=c1|run_id=r1|source_uri=s|chunk_index=0|page=1|start_char=0|end_char=10]"
    assert segments[1] == "Second sentence. [CITATION|chunk_id=c2|run_id=r1|source_uri=s|chunk_index=1|page=1|start_char=11|end_char=20]"


def test_split_into_segments_sentence_boundary_split():
    """_split_into_segments must split a multi-sentence paragraph line into separate
    segments at sentence boundaries (period-space-uppercase)."""
    from demo.stages.retrieval_and_qa import _split_into_segments

    # Two sentences on one line, no citation tokens; should produce two segments.
    answer = "Claim A was observed. Claim B was also observed."
    segments = _split_into_segments(answer)
    assert len(segments) == 2
    assert segments[0] == "Claim A was observed."
    assert segments[1] == "Claim B was also observed."


def test_split_into_segments_bullet_lines_not_split():
    """_split_into_segments must treat bullet lines as atomic units, not splitting them
    at internal sentence boundaries."""
    from demo.stages.retrieval_and_qa import _split_into_segments

    answer = "- Bullet one with two claims. Second claim in bullet. [CITATION|chunk_id=c1|run_id=r1|source_uri=s|chunk_index=0|page=1|start_char=0|end_char=50]"
    segments = _split_into_segments(answer)
    assert len(segments) == 1


def test_split_into_segments_decimal_not_classified_as_bullet():
    """_split_into_segments must NOT treat a decimal number like '1.23 is...' as a bullet.
    The updated _BULLET_PREFIX_RE requires whitespace immediately after the digit-period,
    so '1.23' (digit-period-digit, no space) is correctly classified as a paragraph line."""
    from demo.stages.retrieval_and_qa import _split_into_segments

    # "1.23 is a ratio." — starts with a decimal, should be a paragraph, not a bullet.
    # Sentence splitting should apply; "1.23 is a ratio. Evidence shows..." splits.
    answer = "1.23 is a ratio. Evidence shows a correlation."
    segments = _split_into_segments(answer)
    # Not a bullet, so sentence splitting applies at ". E" (uppercase E).
    assert len(segments) == 2
    assert segments[0] == "1.23 is a ratio."
    assert segments[1] == "Evidence shows a correlation."


def test_split_into_segments_quoted_sentence_split():
    """_split_into_segments must split at a sentence boundary even when the next
    sentence begins with an opening quotation mark before the uppercase letter."""
    from demo.stages.retrieval_and_qa import _split_into_segments

    # "Claim A. "Claim B..." — period-space-quote-uppercase triggers the split.
    answer = 'Claim A. "Claim B was also observed.'
    segments = _split_into_segments(answer)
    assert len(segments) == 2
    assert segments[0] == "Claim A."
    assert segments[1] == '"Claim B was also observed.'


def test_split_into_segments_no_split_inside_citation_tokens():
    """_split_into_segments must not split inside or immediately after citation tokens
    even when they appear between sentences."""
    from demo.stages.retrieval_and_qa import _split_into_segments

    # Citation token appears between two sentences; the negative lookahead
    # (?!CITATION\|) in _SENTENCE_SPLIT_RE blocks the split at ". [CITATION|",
    # keeping the whole line as a single segment.
    answer = (
        "Claim A. "
        "[CITATION|chunk_id=c1|run_id=r1|source_uri=file:///x.pdf|chunk_index=0|page=1|start_char=0|end_char=20] "
        "Claim B. "
        "[CITATION|chunk_id=c2|run_id=r1|source_uri=file:///x.pdf|chunk_index=1|page=1|start_char=21|end_char=40]"
    )
    segments = _split_into_segments(answer)
    # The period in "Claim A." is followed by " [CITATION..." — the negative lookahead
    # (?!CITATION\|) prevents a split here.  After the citation token ends with ']',
    # the lookbehind (?<=[.!?]) fails because ']' is not in [.!?].
    # Therefore no sentence split fires and all text forms a single segment.
    assert len(segments) == 1


def test_split_into_segments_non_citation_bracket_triggers_split():
    """_split_into_segments must split at a sentence boundary even when the next
    'sentence' begins with a non-citation bracket (e.g. [Note], [1]).
    This prevents an uncited sentence from being hidden behind such a bracket."""
    from demo.stages.retrieval_and_qa import _split_into_segments

    # "Claim A." is followed by "[Note]" (a non-citation bracket), then "Claim B."
    # with a citation.  Only Claim B is cited; the split must expose Claim A as
    # uncited.
    answer = (
        "Claim A. "
        "[Note] "
        "Claim B. "
        "[CITATION|chunk_id=c1|run_id=r1|source_uri=file:///x.pdf|chunk_index=0|page=1|start_char=0|end_char=50]"
    )
    segments = _split_into_segments(answer)
    # ". [Note]" triggers a split because "\[(?!CITATION\|)" matches "[Note".
    assert len(segments) == 2
    assert segments[0] == "Claim A."
    assert segments[1].startswith("[Note]")


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
        "demo.stages.retrieval_and_qa.build_openai_llm"
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
        "demo.stages.retrieval_and_qa.build_openai_llm"
    ), mock.patch("neo4j.GraphDatabase.driver"), mock.patch.dict(os.environ, {"OPENAI_API_KEY": "test-key"}):
        result = run_retrieval_and_qa(
            live_config,
            run_id="live-run-uncited",
            source_uri=None,
            question="What happened?",
        )

    assert result["all_answers_cited"] is False
    assert any("citation" in w.lower() for w in result["warnings"])


def test_retrieval_and_qa_live_path_applies_fallback_when_uncited(tmp_path: Path):
    """Live path must replace the answer with a structured fallback message when the
    answer contains uncited sentences, and preserve the original in raw_answer."""
    from demo.stages import run_retrieval_and_qa
    from demo.stages.retrieval_and_qa import _CITATION_FALLBACK_PREFIX

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
        "demo.stages.retrieval_and_qa.build_openai_llm"
    ), mock.patch("neo4j.GraphDatabase.driver"), mock.patch.dict(os.environ, {"OPENAI_API_KEY": "test-key"}):
        result = run_retrieval_and_qa(
            live_config,
            run_id="live-run-fallback",
            source_uri=None,
            question="What happened?",
        )

    # answer must be replaced with the structured fallback prefix
    assert result["answer"].startswith(_CITATION_FALLBACK_PREFIX + ":")
    # raw_answer must contain the original LLM output
    assert result["raw_answer"] == uncited_answer
    # answer and raw_answer must differ (fallback was applied)
    assert result["answer"] != result["raw_answer"]


def test_retrieval_and_qa_live_path_no_fallback_when_fully_cited(tmp_path: Path):
    """Live path must NOT apply a fallback when all answer sentences are cited: answer
    must equal the original LLM output and raw_answer must also match."""
    from demo.stages import run_retrieval_and_qa
    from demo.stages.retrieval_and_qa import _CITATION_FALLBACK_PREFIX

    cited_answer = (
        "All claims are supported. [CITATION|chunk_id=c1|run_id=live-ok|"
        "source_uri=file:///doc.pdf|chunk_index=0|page=1|start_char=0|end_char=10]"
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
        "demo.stages.retrieval_and_qa.build_openai_llm"
    ), mock.patch("neo4j.GraphDatabase.driver"), mock.patch.dict(os.environ, {"OPENAI_API_KEY": "test-key"}):
        result = run_retrieval_and_qa(
            live_config,
            run_id="live-ok",
            source_uri=None,
            question="What happened?",
        )

    # No fallback for fully cited answers
    assert not result["answer"].startswith(_CITATION_FALLBACK_PREFIX)
    assert result["answer"] == cited_answer
    assert result["raw_answer"] == cited_answer


def test_run_interactive_qa_shows_fallback_message_when_uncited(
    tmp_path: Path, capsys: pytest.CaptureFixture
):
    """run_interactive_qa must print the structured fallback message (including the original
    uncited answer text) when the LLM returns a response without proper citation tokens."""
    from demo.stages.retrieval_and_qa import run_interactive_qa, _CITATION_FALLBACK_PREFIX

    uncited_answer = "This claim has no citation and is not grounded."

    class _FakeRetriever:
        def __init__(self, **kwargs):
            pass

        def search(self, **kwargs):
            return _make_fake_retriever_result([])

    class _FakeGraphRAG:
        def __init__(self, *, retriever, llm, prompt_template=None):
            pass

        def search(self, *, query_text="", retriever_config=None, return_context=None, message_history=None, **kwargs):
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

    inputs = iter(["What happened?"])

    def _fake_input(_prompt=""):
        try:
            return next(inputs)
        except StopIteration:
            raise EOFError

    with mock.patch("demo.stages.retrieval_and_qa.VectorCypherRetriever", _FakeRetriever), mock.patch(
        "demo.stages.retrieval_and_qa.OpenAIEmbeddings"
    ), mock.patch("demo.stages.retrieval_and_qa.GraphRAG", _FakeGraphRAG), mock.patch(
        "demo.stages.retrieval_and_qa.build_openai_llm"
    ), mock.patch("neo4j.GraphDatabase.driver"), mock.patch.dict(
        os.environ, {"OPENAI_API_KEY": "test-key"}
    ), mock.patch("builtins.input", _fake_input):
        run_interactive_qa(live_config, run_id="interactive-run-fallback")

    captured = capsys.readouterr()
    # The fallback prefix must appear in the printed answer
    assert _CITATION_FALLBACK_PREFIX in captured.out
    # The raw uncited answer text should still be visible (embedded in the fallback message)
    assert uncited_answer in captured.out


def test_run_interactive_qa_does_not_show_fallback_when_fully_cited(
    tmp_path: Path, capsys: pytest.CaptureFixture
):
    """run_interactive_qa must print the answer as-is (no fallback prefix) when every
    answer sentence ends with a citation token."""
    from demo.stages.retrieval_and_qa import run_interactive_qa, _CITATION_FALLBACK_PREFIX

    cited_answer = (
        "All claims are supported. [CITATION|chunk_id=c1|run_id=r1|"
        "source_uri=file:///doc.pdf|chunk_index=0|page=1|start_char=0|end_char=10]"
    )

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
        "demo.stages.retrieval_and_qa.build_openai_llm"
    ), mock.patch("neo4j.GraphDatabase.driver"), mock.patch.dict(
        os.environ, {"OPENAI_API_KEY": "test-key"}
    ), mock.patch("builtins.input", _fake_input):
        run_interactive_qa(live_config, run_id="interactive-run-no-fallback")

    captured = capsys.readouterr()
    # No fallback prefix for fully cited answers
    assert _CITATION_FALLBACK_PREFIX not in captured.out


def test_retrieval_and_qa_live_path_fallback_answer_contains_original_text(tmp_path: Path):
    """The fallback answer must embed the original (uncited) LLM output so the
    specific uncited content is visible in logs and artifacts."""
    from demo.stages import run_retrieval_and_qa
    from demo.stages.retrieval_and_qa import _CITATION_FALLBACK_PREFIX

    uncited_answer = "The suspect was identified at the scene without any citation."

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
        "demo.stages.retrieval_and_qa.build_openai_llm"
    ), mock.patch("neo4j.GraphDatabase.driver"), mock.patch.dict(os.environ, {"OPENAI_API_KEY": "test-key"}):
        result = run_retrieval_and_qa(
            live_config,
            run_id="live-run-embed",
            source_uri=None,
            question="Who was identified?",
        )

    # The fallback answer must embed the original text so it can be surfaced in artifacts
    assert uncited_answer in result["answer"]
    assert result["answer"] == f"{_CITATION_FALLBACK_PREFIX}: {uncited_answer}"


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
        "demo.stages.retrieval_and_qa.build_openai_llm"
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
    """Live path must create an LLM with the model from config via build_openai_llm."""
    from demo.stages import run_retrieval_and_qa

    captured_llm_calls: list = []

    class _FakeRetriever:
        def __init__(self, **kwargs):
            pass

        def search(self, **kwargs):
            return _make_fake_retriever_result([])

    class _FakeLLM:
        def __init__(self, model_name, model_params=None):
            pass

    def _fake_build_openai_llm(model_name):
        captured_llm_calls.append(model_name)
        return _FakeLLM(model_name)

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
        "demo.stages.retrieval_and_qa.build_openai_llm", _fake_build_openai_llm
    ), mock.patch("neo4j.GraphDatabase.driver"), mock.patch.dict(os.environ, {"OPENAI_API_KEY": "test-key"}):
        run_retrieval_and_qa(
            live_config,
            run_id="live-run-llm",
            source_uri=None,
            question="Test question",
        )

    assert captured_llm_calls == ["gpt-4o"]


def test_retrieval_and_qa_live_path_uses_power_atlas_prompt_template(tmp_path: Path):
    """Live path must pass the Power Atlas citation-enforcing prompt template to GraphRAG."""
    from demo.stages import run_retrieval_and_qa

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
        "demo.stages.retrieval_and_qa.build_openai_llm"
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
        "demo.stages.retrieval_and_qa.build_openai_llm"
    ), mock.patch("neo4j.GraphDatabase.driver"), mock.patch.dict(os.environ, {"OPENAI_API_KEY": "test-key"}):
        result = run_retrieval_and_qa(
            no_model_config,
            run_id="live-run-no-model",
            source_uri=None,
            question="Test?",
        )

    assert result["qa_model"] is not None
    assert result["qa_model"] != ""
    assert result["qa_model"] == "gpt-5.4"


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

    class _FakeGraphRAG:
        def __init__(self, *, retriever, llm, prompt_template=None):
            pass

        def search(self, *, query_text="", retriever_config=None, return_context=None, message_history=None, **kwargs):
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
        "demo.stages.retrieval_and_qa.build_openai_llm"
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
        "demo.stages.retrieval_and_qa.build_openai_llm"
    ), mock.patch("neo4j.GraphDatabase.driver"), mock.patch.dict(
        os.environ, {"OPENAI_API_KEY": "test-key"}
    ), mock.patch("builtins.input", _fake_input):
        run_interactive_qa(live_config, run_id="interactive-run-cited")

    captured = capsys.readouterr()
    assert "WARNING" not in captured.out and "degraded" not in captured.out.lower()


# ---------------------------------------------------------------------------
# citation_quality per-answer QA signals
# ---------------------------------------------------------------------------


def test_retrieval_and_qa_dry_run_includes_citation_quality(tmp_path: Path):
    """Dry-run result must include a citation_quality dict with the required keys and
    default 'no_answer' evidence_level since no answer is generated during dry-run."""
    from demo.stages import run_retrieval_and_qa

    config = _dry_run_config(tmp_path)
    result = run_retrieval_and_qa(config, run_id="qa-dry", source_uri=None)

    assert "citation_quality" in result
    cq = result["citation_quality"]
    assert isinstance(cq, dict)
    required_cq_keys = {"all_cited", "evidence_level", "warning_count", "citation_warnings"}
    assert required_cq_keys.issubset(cq.keys())
    assert cq["evidence_level"] == "no_answer"
    assert cq["all_cited"] is False
    assert cq["warning_count"] == 0
    assert cq["citation_warnings"] == []


def test_retrieval_and_qa_dry_run_includes_raw_answer(tmp_path: Path):
    """Dry-run result must include a raw_answer key (defaulting to '') so the
    result schema is stable across all return paths."""
    from demo.stages import run_retrieval_and_qa

    config = _dry_run_config(tmp_path)
    result = run_retrieval_and_qa(config, run_id="qa-dry-raw", source_uri=None)

    assert "raw_answer" in result
    assert result["raw_answer"] == ""


def test_retrieval_and_qa_live_no_question_includes_raw_answer(tmp_path: Path):
    """Live early-return when question=None must include raw_answer in result."""
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

    with mock.patch("neo4j.GraphDatabase.driver"), mock.patch.dict(os.environ, {"OPENAI_API_KEY": "test-key"}):
        result = run_retrieval_and_qa(live_config, run_id="live-no-q", source_uri=None, question=None)

    assert "raw_answer" in result
    assert result["raw_answer"] == ""


def test_retrieval_and_qa_dry_run_includes_citation_fallback_applied(tmp_path: Path):
    """Dry-run result must include citation_fallback_applied (False) so the result
    schema is stable across all return paths."""
    from demo.stages import run_retrieval_and_qa

    config = _dry_run_config(tmp_path)
    result = run_retrieval_and_qa(config, run_id="qa-dry-flag", source_uri=None)

    assert "citation_fallback_applied" in result
    assert result["citation_fallback_applied"] is False


def test_retrieval_and_qa_live_no_question_includes_citation_fallback_applied(tmp_path: Path):
    """Live early-return when question=None must include citation_fallback_applied (False)."""
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

    with mock.patch("neo4j.GraphDatabase.driver"), mock.patch.dict(os.environ, {"OPENAI_API_KEY": "test-key"}):
        result = run_retrieval_and_qa(live_config, run_id="live-no-q-flag", source_uri=None, question=None)

    assert "citation_fallback_applied" in result
    assert result["citation_fallback_applied"] is False


def test_retrieval_and_qa_live_path_sets_citation_fallback_applied_true_when_uncited(tmp_path: Path):
    """When the LLM returns an uncited answer, citation_fallback_applied must be True so
    consumers can detect fallback application via explicit metadata rather than string-prefix
    matching."""
    from demo.stages import run_retrieval_and_qa

    uncited_answer = "This answer has no citation tokens at all."

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
    ), mock.patch(
        "demo.stages.retrieval_and_qa.GraphRAG", _make_stub_graphrag_class(answer=uncited_answer)
    ), mock.patch("demo.stages.retrieval_and_qa.build_openai_llm"), mock.patch(
        "neo4j.GraphDatabase.driver"
    ), mock.patch.dict(os.environ, {"OPENAI_API_KEY": "test-key"}):
        result = run_retrieval_and_qa(
            live_config,
            run_id="live-uncited-flag",
            source_uri=None,
            question="Any question?",
        )

    assert result["citation_fallback_applied"] is True
    assert result["raw_answer"] == uncited_answer
    assert result["all_answers_cited"] is False


def test_retrieval_and_qa_live_path_citation_fallback_applied_false_when_cited(tmp_path: Path):
    """When the LLM returns a fully-cited answer, citation_fallback_applied must be False."""
    from demo.stages import run_retrieval_and_qa

    cited_answer = "Power is important.[CITATION|chunk_id=abc|run_id=r|source_uri=s|chunk_index=0|page=1|start_char=0|end_char=10]"

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
    ), mock.patch(
        "demo.stages.retrieval_and_qa.GraphRAG", _make_stub_graphrag_class(answer=cited_answer)
    ), mock.patch("demo.stages.retrieval_and_qa.build_openai_llm"), mock.patch(
        "neo4j.GraphDatabase.driver"
    ), mock.patch.dict(os.environ, {"OPENAI_API_KEY": "test-key"}):
        result = run_retrieval_and_qa(
            live_config,
            run_id="live-cited-flag",
            source_uri=None,
            question="Any question?",
        )

    assert result["citation_fallback_applied"] is False
    assert result["all_answers_cited"] is True


def test_run_interactive_qa_stores_refusal_prefix_in_history(
    tmp_path: Path,
):
    """run_interactive_qa must store only the sanitized refusal prefix (not the full
    fallback text embedding the uncited output) in conversation history so subsequent
    turns are not conditioned on under-cited content."""
    from demo.stages.retrieval_and_qa import run_interactive_qa, _CITATION_FALLBACK_PREFIX
    from neo4j_graphrag.message_history import InMemoryMessageHistory

    uncited_answer = "This claim has no citation and is not grounded."
    captured_history_messages: list = []

    class _FakeRetriever:
        def __init__(self, **kwargs):
            pass

        def search(self, **kwargs):
            return _make_fake_retriever_result([])

    class _FakeGraphRAG:
        def __init__(self, *, retriever, llm, prompt_template=None):
            pass

        def search(self, *, query_text="", retriever_config=None, return_context=None, message_history=None, **kwargs):
            # Capture the history state after this turn completes via add_messages side-effect
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

    inputs = iter(["What happened?"])

    def _fake_input(_prompt=""):
        try:
            return next(inputs)
        except StopIteration:
            raise EOFError

    _original_add_messages = InMemoryMessageHistory.add_messages

    def _capturing_add_messages(self, messages):
        captured_history_messages.extend(messages)
        return _original_add_messages(self, messages)

    with mock.patch("demo.stages.retrieval_and_qa.VectorCypherRetriever", _FakeRetriever), mock.patch(
        "demo.stages.retrieval_and_qa.OpenAIEmbeddings"
    ), mock.patch("demo.stages.retrieval_and_qa.GraphRAG", _FakeGraphRAG), mock.patch(
        "demo.stages.retrieval_and_qa.build_openai_llm"
    ), mock.patch("neo4j.GraphDatabase.driver"), mock.patch.dict(
        os.environ, {"OPENAI_API_KEY": "test-key"}
    ), mock.patch("builtins.input", _fake_input), mock.patch.object(
        InMemoryMessageHistory, "add_messages", _capturing_add_messages
    ):
        run_interactive_qa(live_config, run_id="interactive-history-fallback")

    # The assistant message in history must be only the sanitized refusal prefix —
    # NOT the full fallback (which embeds the uncited output) and NOT the raw uncited answer.
    # LLMMessage is a TypedDict (dict subtype), so access via dict keys.
    assistant_msgs = [m for m in captured_history_messages if m.get("role") == "assistant"]
    assert len(assistant_msgs) == 1
    assert assistant_msgs[0]["content"] == _CITATION_FALLBACK_PREFIX
    assert uncited_answer not in assistant_msgs[0]["content"]


def test_retrieval_and_qa_live_path_citation_quality_full_when_all_cited(tmp_path: Path):
    """Live path must set citation_quality.evidence_level='full' and all_cited=True
    when the generated answer contains citation tokens on every line."""
    from demo.stages import run_retrieval_and_qa

    cited_answer = (
        "Evidence was found. [CITATION|chunk_id=c1|run_id=live-cq|"
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
        "demo.stages.retrieval_and_qa.build_openai_llm"
    ), mock.patch("neo4j.GraphDatabase.driver"), mock.patch.dict(os.environ, {"OPENAI_API_KEY": "test-key"}):
        result = run_retrieval_and_qa(
            live_config,
            run_id="live-cq",
            source_uri=None,
            question="What happened?",
        )

    cq = result["citation_quality"]
    assert cq["all_cited"] is True
    assert cq["evidence_level"] == "full"
    assert cq["warning_count"] == 0
    assert cq["citation_warnings"] == []


def test_retrieval_and_qa_live_path_citation_quality_degraded_when_uncited(tmp_path: Path):
    """Live path must set citation_quality.evidence_level='degraded' and all_cited=False
    when the generated answer contains lines without citation tokens."""
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
        "demo.stages.retrieval_and_qa.build_openai_llm"
    ), mock.patch("neo4j.GraphDatabase.driver"), mock.patch.dict(os.environ, {"OPENAI_API_KEY": "test-key"}):
        result = run_retrieval_and_qa(
            live_config,
            run_id="live-cq-uncited",
            source_uri=None,
            question="What happened?",
        )

    cq = result["citation_quality"]
    assert cq["all_cited"] is False
    assert cq["evidence_level"] == "degraded"
    assert cq["warning_count"] >= 1
    assert any("citation" in w.lower() for w in cq["citation_warnings"])


def test_retrieval_and_qa_live_path_citation_quality_no_answer_when_empty(tmp_path: Path):
    """Live path must set citation_quality.evidence_level='no_answer' when the LLM
    returns an empty answer string."""
    from demo.stages import run_retrieval_and_qa

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
    ), mock.patch("demo.stages.retrieval_and_qa.GraphRAG", _make_stub_graphrag_class(answer="")), mock.patch(
        "demo.stages.retrieval_and_qa.build_openai_llm"
    ), mock.patch("neo4j.GraphDatabase.driver"), mock.patch.dict(os.environ, {"OPENAI_API_KEY": "test-key"}):
        result = run_retrieval_and_qa(
            live_config,
            run_id="live-cq-empty",
            source_uri=None,
            question="What happened?",
        )

    cq = result["citation_quality"]
    assert cq["all_cited"] is False
    assert cq["evidence_level"] == "no_answer"


# ---------------------------------------------------------------------------
# batch-level qa_signals in build_batch_manifest
# ---------------------------------------------------------------------------


def test_batch_manifest_includes_qa_signals(tmp_path: Path):
    """build_batch_manifest must include a top-level qa_signals dict that summarises
    citation quality without requiring consumers to inspect stage-level details."""
    config = _dry_run_config(tmp_path)
    retrieval_stage = {
        "status": "dry_run",
        "all_answers_cited": False,
        "warnings": [],
        "citation_quality": {
            "all_cited": False,
            "evidence_level": "no_answer",
            "warning_count": 0,
            "citation_warnings": [],
        },
    }
    manifest = build_batch_manifest(
        config=config,
        structured_run_id="structured-1",
        unstructured_run_id="unstructured-2",
        structured_stage={"status": "dry_run"},
        pdf_stage={"status": "dry_run"},
        claim_stage={"status": "dry_run"},
        retrieval_stage=retrieval_stage,
    )

    assert "qa_signals" in manifest
    qa_signals = manifest["qa_signals"]
    required_keys = {"all_answers_cited", "evidence_level", "warning_count", "warnings"}
    assert required_keys.issubset(qa_signals.keys())
    assert qa_signals["evidence_level"] == "no_answer"
    assert qa_signals["all_answers_cited"] is False
    assert qa_signals["warning_count"] == 0
    assert qa_signals["warnings"] == []


def test_batch_manifest_qa_signals_reflects_retrieval_stage_quality(tmp_path: Path):
    """qa_signals in the batch manifest must mirror the citation quality from the
    retrieval stage so batch-level consumers get accurate signal values."""
    config = _dry_run_config(tmp_path)
    # Simulate a retrieval stage result where the answer was fully cited
    retrieval_stage = {
        "status": "live",
        "all_answers_cited": True,
        "warnings": [],
        "citation_quality": {
            "all_cited": True,
            "evidence_level": "full",
            "warning_count": 0,
            "citation_warnings": [],
        },
    }
    manifest = build_batch_manifest(
        config=config,
        structured_run_id="s1",
        unstructured_run_id="u1",
        structured_stage={"status": "dry_run"},
        pdf_stage={"status": "dry_run"},
        claim_stage={"status": "dry_run"},
        retrieval_stage=retrieval_stage,
    )

    qa_signals = manifest["qa_signals"]
    assert qa_signals["all_answers_cited"] is True
    assert qa_signals["evidence_level"] == "full"
    assert qa_signals["warning_count"] == 0


def test_batch_manifest_qa_signals_degraded_when_uncited(tmp_path: Path):
    """qa_signals.evidence_level must be 'degraded' when the retrieval stage recorded
    an uncited answer, so the batch manifest accurately reflects QA quality."""
    config = _dry_run_config(tmp_path)
    warning_text = "Not all non-empty answer lines end with a citation token."
    retrieval_stage = {
        "status": "live",
        "all_answers_cited": False,
        "warnings": [warning_text],
        "citation_quality": {
            "all_cited": False,
            "evidence_level": "degraded",
            "warning_count": 1,
            "citation_warnings": [warning_text],
        },
    }
    manifest = build_batch_manifest(
        config=config,
        structured_run_id="s1",
        unstructured_run_id="u1",
        structured_stage={"status": "dry_run"},
        pdf_stage={"status": "dry_run"},
        claim_stage={"status": "dry_run"},
        retrieval_stage=retrieval_stage,
    )

    qa_signals = manifest["qa_signals"]
    assert qa_signals["all_answers_cited"] is False
    assert qa_signals["evidence_level"] == "degraded"
    assert qa_signals["warning_count"] == 1
    assert warning_text in qa_signals["warnings"]


def test_batch_manifest_qa_signals_defaults_when_retrieval_stage_missing_signals(tmp_path: Path):
    """qa_signals must use safe defaults (no_answer, warning_count=0) when the
    retrieval stage result does not contain citation_quality or warnings."""
    config = _dry_run_config(tmp_path)
    # Retrieval stage without citation_quality (simulates legacy stage output)
    retrieval_stage = {"status": "dry_run"}
    manifest = build_batch_manifest(
        config=config,
        structured_run_id="s1",
        unstructured_run_id="u1",
        structured_stage={"status": "dry_run"},
        pdf_stage={"status": "dry_run"},
        claim_stage={"status": "dry_run"},
        retrieval_stage=retrieval_stage,
    )

    qa_signals = manifest["qa_signals"]
    assert qa_signals["all_answers_cited"] is False
    assert qa_signals["evidence_level"] == "no_answer"
    assert qa_signals["warning_count"] == 0
    assert qa_signals["warnings"] == []


def test_retrieval_and_qa_live_path_citation_quality_full_when_only_optional_fields_missing(tmp_path: Path):
    """evidence_level must be 'full' (not 'degraded') when the answer is fully cited and
    only optional citation fields (page/start_char/end_char) are missing from chunks.
    Per citation contract #159, page/start_char/end_char are optional; their absence
    must not degrade evidence_level.  The missing-field notice must appear in
    result['warnings'] but NOT in citation_quality['citation_warnings']."""
    from demo.stages import run_retrieval_and_qa

    # A fully cited answer (every line ends with a citation token)
    cited_answer = (
        "Evidence was found. [CITATION|chunk_id=chunk-no-page|run_id=live-cq-chunk|"
        "source_uri=file:///x.pdf|chunk_index=0|page=|start_char=|end_char=]"
    )

    # A chunk missing all optional citation fields
    fake_meta = {
        "chunk_id": "chunk-no-page",
        "run_id": "live-cq-chunk",
        "source_uri": "file:///x.pdf",
        "chunk_index": 0,
        "page": None,
        "start_char": None,
        "end_char": None,
        "score": 0.9,
        "citation_token": (
            "[CITATION|chunk_id=chunk-no-page|run_id=live-cq-chunk|"
            "source_uri=file:///x.pdf|chunk_index=0|page=|start_char=|end_char=]"
        ),
        "citation_object": {
            "chunk_id": "chunk-no-page",
            "run_id": "live-cq-chunk",
            "source_uri": "file:///x.pdf",
            "chunk_index": 0,
            "page": None,
            "start_char": None,
            "end_char": None,
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
    ), mock.patch("demo.stages.retrieval_and_qa.GraphRAG", _make_stub_graphrag_class(answer=cited_answer)), mock.patch(
        "demo.stages.retrieval_and_qa.build_openai_llm"
    ), mock.patch("neo4j.GraphDatabase.driver"), mock.patch.dict(os.environ, {"OPENAI_API_KEY": "test-key"}):
        result = run_retrieval_and_qa(
            live_config,
            run_id="live-cq-chunk",
            source_uri=None,
            question="What happened?",
        )

    cq = result["citation_quality"]
    # all_cited is True and evidence_level must be 'full': optional fields (page,
    # start_char, end_char) absent does NOT degrade evidence per citation contract #159.
    assert cq["all_cited"] is True
    assert cq["evidence_level"] == "full", (
        "evidence_level must be 'full' when all answers are cited; "
        "missing optional citation fields (page/start_char/end_char) must not degrade quality"
    )
    assert cq["warning_count"] == 0
    assert cq["citation_warnings"] == []
    # The missing-field notice must still appear in the general warnings list with
    # the expected format indicating it's an optional-field notice.
    general_warnings = result.get("warnings", [])
    assert any(
        "chunk-no-page" in w and "optional citation fields" in w
        for w in general_warnings
    ), f"Expected optional-field warning for chunk-no-page in warnings, got: {general_warnings}"


# ---------------------------------------------------------------------------
# Empty chunk text warnings
# ---------------------------------------------------------------------------


def test_chunk_citation_formatter_sets_empty_chunk_text_flag_when_blank(tmp_path: Path):
    """_chunk_citation_formatter must set empty_chunk_text=True in metadata when the
    retrieved chunk has empty or whitespace-only text."""
    from demo.stages.retrieval_and_qa import _chunk_citation_formatter

    # Whitespace-only text should trigger the flag.
    for blank_text in ("", "   ", "\t\n"):
        record = _make_fake_neo4j_record(
            chunk_id="chunk-empty",
            run_id="r1",
            source_uri="file:///doc.pdf",
            chunk_index=0,
            page=1,
            start_char=0,
            end_char=100,
            chunk_text=blank_text,
            similarityScore=0.9,
        )
        item = _chunk_citation_formatter(record)
        assert item.metadata is not None
        assert item.metadata.get("empty_chunk_text") is True, (
            f"Expected empty_chunk_text=True for chunk_text={blank_text!r}"
        )


def test_chunk_citation_formatter_empty_chunk_text_false_when_has_content(tmp_path: Path):
    """_chunk_citation_formatter must set empty_chunk_text=False when the chunk has
    non-whitespace text."""
    from demo.stages.retrieval_and_qa import _chunk_citation_formatter

    record = _make_fake_neo4j_record(
        chunk_id="chunk-full",
        run_id="r1",
        source_uri="file:///doc.pdf",
        chunk_index=0,
        page=1,
        start_char=0,
        end_char=100,
        chunk_text="This is meaningful content.",
        similarityScore=0.95,
    )
    item = _chunk_citation_formatter(record)
    assert item.metadata is not None
    assert item.metadata.get("empty_chunk_text") is False


def test_retrieval_and_qa_live_path_warns_on_empty_chunk_text(tmp_path: Path):
    """Live path must emit a warning into warnings and citation_warnings when a
    retrieved chunk has empty or whitespace-only text, and evidence_level must be
    'degraded' even when the answer is otherwise fully cited."""
    from demo.stages import run_retrieval_and_qa

    cited_answer = (
        "Evidence was found. [CITATION|chunk_id=chunk-empty|run_id=live-empty-text|"
        "source_uri=file:///x.pdf|chunk_index=0|page=1|start_char=0|end_char=50]"
    )

    # A chunk with empty text but otherwise complete citation metadata.
    citation_token = (
        "[CITATION|chunk_id=chunk-empty|run_id=live-empty-text|"
        "source_uri=file:///x.pdf|chunk_index=0|page=1|start_char=0|end_char=50]"
    )
    fake_meta = {
        "chunk_id": "chunk-empty",
        "run_id": "live-empty-text",
        "source_uri": "file:///x.pdf",
        "chunk_index": 0,
        "page": 1,
        "start_char": 0,
        "end_char": 50,
        "score": 0.88,
        "citation_token": citation_token,
        "citation_object": {
            "chunk_id": "chunk-empty",
            "run_id": "live-empty-text",
            "source_uri": "file:///x.pdf",
            "chunk_index": 0,
            "page": 1,
            "start_char": 0,
            "end_char": 50,
        },
        "empty_chunk_text": True,
    }
    fake_item = _make_fake_retriever_result_item(
        content="\n" + citation_token,
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
    ), mock.patch("demo.stages.retrieval_and_qa.GraphRAG", _make_stub_graphrag_class(answer=cited_answer)), mock.patch(
        "demo.stages.retrieval_and_qa.build_openai_llm"
    ), mock.patch("neo4j.GraphDatabase.driver"), mock.patch.dict(os.environ, {"OPENAI_API_KEY": "test-key"}):
        result = run_retrieval_and_qa(
            live_config,
            run_id="live-empty-text",
            source_uri=None,
            question="What happened?",
        )

    # Empty chunk text warning must appear in warnings and citation_warnings.
    assert any("chunk-empty" in w and "empty" in w.lower() for w in result["warnings"]), (
        "Expected an empty-chunk-text warning in result['warnings']"
    )
    cq = result["citation_quality"]
    assert any("chunk-empty" in w and "empty" in w.lower() for w in cq["citation_warnings"]), (
        "Expected an empty-chunk-text warning in citation_quality['citation_warnings']"
    )
    # evidence_level must be 'degraded' due to the empty chunk text warning.
    assert cq["evidence_level"] == "degraded", (
        "evidence_level must be 'degraded' when a chunk has empty text"
    )
    assert cq["warning_count"] >= 1


def test_chunk_citation_formatter_emits_log_warning_for_empty_text(tmp_path: Path):
    """_chunk_citation_formatter must emit a logger.warning when chunk text is empty
    or whitespace-only, signalling the issue at retrieval time."""
    from demo.stages.retrieval_and_qa import _chunk_citation_formatter

    record = _make_fake_neo4j_record(
        chunk_id="chunk-log-empty",
        run_id="r1",
        source_uri="file:///doc.pdf",
        chunk_index=0,
        page=1,
        start_char=0,
        end_char=100,
        chunk_text="",
        similarityScore=0.8,
    )

    with mock.patch("demo.stages.retrieval_and_qa._logger") as mock_logger:
        _chunk_citation_formatter(record)
        mock_logger.warning.assert_called_once()
        args, _kwargs = mock_logger.warning.call_args
        # The format string must describe empty/whitespace chunk text.
        assert args, "Expected logger.warning to be called with at least a message format string"
        warning_msg = str(args[0])
        lower_msg = warning_msg.lower()
        assert ("empty" in lower_msg) or ("whitespace" in lower_msg), (
            f"Expected warning message to mention empty/whitespace text, got: {warning_msg!r}"
        )
        # The chunk_id must be passed as a separate format argument, not embedded in the format string.
        assert len(args) >= 2, "Expected chunk_id to be passed as a separate argument to logger.warning"
        assert args[1] == "chunk-log-empty"


# ---------------------------------------------------------------------------
# Tests for ask mode retrieval scope: --run-id, --latest, --all-runs (issue #230)
# ---------------------------------------------------------------------------


def test_parse_args_ask_accepts_run_id_flag():
    """--run-id flag must set args.run_id for the ask subcommand."""
    from demo.run_demo import parse_args

    args = parse_args(["--dry-run", "ask", "--run-id", "unstructured_ingest-test-123"])
    assert args.run_id == "unstructured_ingest-test-123"
    assert args.all_runs is False
    assert args.latest is False


def test_parse_args_ask_accepts_latest_flag():
    """--latest flag must set args.latest=True for the ask subcommand."""
    from demo.run_demo import parse_args

    args = parse_args(["--dry-run", "ask", "--latest"])
    assert args.latest is True
    assert args.run_id is None
    assert args.all_runs is False


def test_parse_args_ask_accepts_all_runs_flag():
    """--all-runs flag must set args.all_runs=True for the ask subcommand."""
    from demo.run_demo import parse_args

    args = parse_args(["--dry-run", "ask", "--all-runs"])
    assert args.all_runs is True
    assert args.run_id is None
    assert args.latest is False


def test_parse_args_ask_scope_flags_mutually_exclusive():
    """--run-id, --latest, and --all-runs must be mutually exclusive."""
    from demo.run_demo import parse_args

    with pytest.raises(SystemExit):
        parse_args(["--dry-run", "ask", "--run-id", "some-id", "--all-runs"])

    with pytest.raises(SystemExit):
        parse_args(["--dry-run", "ask", "--latest", "--all-runs"])

    with pytest.raises(SystemExit):
        parse_args(["--dry-run", "ask", "--run-id", "some-id", "--latest"])


def test_parse_args_ask_no_scope_flag_defaults_to_false():
    """When no scope flag is given, all scope flags default to False/None."""
    from demo.run_demo import parse_args

    args = parse_args(["--dry-run", "ask"])
    assert args.run_id is None
    assert args.latest is False
    assert args.all_runs is False


def test_run_retrieval_and_qa_all_runs_dry_run(tmp_path: Path):
    """all_runs=True must be accepted in dry-run mode; retrieval_scope must reflect all_runs."""
    from demo.stages import run_retrieval_and_qa

    config = _dry_run_config(tmp_path)
    result = run_retrieval_and_qa(config, run_id=None, source_uri=None, all_runs=True)
    assert result["status"] == "dry_run"
    scope = result["retrieval_scope"]
    assert scope["all_runs"] is True
    assert scope["scope_widened"] is True
    # run_id should be None in all_runs dry-run mode
    assert scope["run_id"] is None


def test_run_retrieval_and_qa_all_runs_scope_in_result(tmp_path: Path):
    """retrieval_scope must record all_runs=True and scope_widened=True."""
    from demo.stages import run_retrieval_and_qa

    config = _dry_run_config(tmp_path)
    result = run_retrieval_and_qa(config, run_id="some-run", source_uri=None, all_runs=True)
    # run_id is ignored in all_runs mode
    assert result["retrieval_scope"]["all_runs"] is True
    assert result["retrieval_scope"]["scope_widened"] is True


def test_run_retrieval_and_qa_run_scoped_scope_in_result(tmp_path: Path):
    """retrieval_scope must record all_runs=False and scope_widened=False for run-scoped mode."""
    from demo.stages import run_retrieval_and_qa

    config = _dry_run_config(tmp_path)
    result = run_retrieval_and_qa(config, run_id="qa-run-scope", source_uri=None, all_runs=False)
    assert result["retrieval_scope"]["all_runs"] is False
    assert result["retrieval_scope"]["scope_widened"] is False
    assert result["retrieval_scope"]["run_id"] == "qa-run-scope"


def test_run_retrieval_and_qa_live_requires_run_id_when_not_all_runs(tmp_path: Path):
    """Live mode must still raise ValueError when run_id is None and all_runs is False."""
    from demo.stages import run_retrieval_and_qa

    live_config = Config(
        dry_run=False,
        output_dir=tmp_path,
        neo4j_uri="bolt://example.invalid",
        neo4j_username="neo4j",
        neo4j_password="secret",
        neo4j_database="neo4j",
        openai_model="gpt-4o-mini",
    )
    with mock.patch.dict(os.environ, {"OPENAI_API_KEY": "test-key"}):
        with pytest.raises(ValueError, match="run_id is required"):
            run_retrieval_and_qa(live_config, run_id=None, source_uri=None, question="Test?", all_runs=False)


def test_run_retrieval_and_qa_live_all_runs_uses_unscoped_query(tmp_path: Path):
    """Live all_runs=True must pass query_params without 'run_id' to the retriever."""
    from demo.stages import run_retrieval_and_qa

    captured_params: dict[str, object] = {}

    class _FakeRetriever:
        def __init__(self, **kwargs):
            self._retrieval_query = kwargs.get("retrieval_query", "")

        def search(self, *, query_text="", top_k=None, query_params=None):
            if query_params is not None:
                captured_params.update(query_params)
            return _make_fake_retriever_result([])

    live_config = Config(
        dry_run=False,
        output_dir=tmp_path,
        neo4j_uri="bolt://example.invalid",
        neo4j_username="neo4j",
        neo4j_password="secret",
        neo4j_database="neo4j",
        openai_model="gpt-4o-mini",
    )

    with mock.patch("demo.stages.retrieval_and_qa.VectorCypherRetriever", _FakeRetriever), mock.patch(
        "demo.stages.retrieval_and_qa.OpenAIEmbeddings"
    ), mock.patch(
        "demo.stages.retrieval_and_qa.GraphRAG", _make_stub_graphrag_class()
    ), mock.patch(
        "demo.stages.retrieval_and_qa.build_openai_llm"
    ), mock.patch(
        "neo4j.GraphDatabase.driver"
    ), mock.patch.dict(os.environ, {"OPENAI_API_KEY": "test-key"}):
        run_retrieval_and_qa(
            live_config,
            run_id=None,
            source_uri=None,
            question="What happened?",
            all_runs=True,
        )

    # all_runs mode must NOT include run_id in query_params
    assert "run_id" not in captured_params, (
        f"all_runs=True must not pass run_id to the retriever; got param keys: {sorted(captured_params.keys())}"
    )
    # source_uri filter must still be present
    assert "source_uri" in captured_params


# ---------------------------------------------------------------------------
# all-runs citation repair: uncited segments are repaired using retrieved tokens
# ---------------------------------------------------------------------------

def test_retrieval_and_qa_live_all_runs_uncited_answer_repaired_when_hits_present(tmp_path: Path):
    """In all_runs mode, uncited answer segments must be repaired using retrieved citation
    tokens rather than applying the generic fallback, when at least one hit with a
    citation token is available.  Result must report all_answers_cited=True,
    citation_fallback_applied=False, and evidence_level='full'."""
    from demo.stages import run_retrieval_and_qa
    from demo.stages.retrieval_and_qa import _build_citation_token

    uncited_answer = "Power Atlas retrieval spans multiple runs. Evidence found in database."

    real_token = _build_citation_token(
        chunk_id="real-chunk-1",
        run_id="real-run-id",
        source_uri="file:///path/to/doc.pdf",
        chunk_index=0,
        page=1,
        start_char=0,
        end_char=100,
    )

    class _FakeRetrieverWithHit:
        def __init__(self, **kwargs):
            pass

        def search(self, **kwargs):
            return _make_fake_retriever_result(
                [
                    _make_fake_retriever_result_item(
                        f"Chunk text\n{real_token}",
                        {
                            "citation_token": real_token,
                            "citation_object": {
                                "chunk_id": "real-chunk-1",
                                "run_id": "real-run-id",
                                "source_uri": "file:///path/to/doc.pdf",
                                "chunk_index": 0,
                                "page": 1,
                                "start_char": 0,
                                "end_char": 100,
                            },
                            "chunk_id": "real-chunk-1",
                            "run_id": "real-run-id",
                            "source_uri": "file:///path/to/doc.pdf",
                            "chunk_index": 0,
                            "page": 1,
                            "start_char": 0,
                            "end_char": 100,
                            "score": 0.9,
                            "empty_chunk_text": False,
                        },
                    )
                ]
            )

    live_config = Config(
        dry_run=False,
        output_dir=tmp_path,
        neo4j_uri="bolt://example.invalid",
        neo4j_username="neo4j",
        neo4j_password="secret",
        neo4j_database="neo4j",
        openai_model="gpt-4o-mini",
    )

    with mock.patch(
        "demo.stages.retrieval_and_qa.VectorCypherRetriever", _FakeRetrieverWithHit
    ), mock.patch(
        "demo.stages.retrieval_and_qa.OpenAIEmbeddings"
    ), mock.patch(
        "demo.stages.retrieval_and_qa.GraphRAG",
        _make_stub_graphrag_class(answer=uncited_answer),
    ), mock.patch(
        "demo.stages.retrieval_and_qa.build_openai_llm"
    ), mock.patch(
        "neo4j.GraphDatabase.driver"
    ), mock.patch.dict(os.environ, {"OPENAI_API_KEY": "test-key"}):
        result = run_retrieval_and_qa(
            live_config,
            run_id=None,
            source_uri=None,
            question="What happened?",
            all_runs=True,
        )

    assert result["all_answers_cited"] is True, (
        "all-runs mode must repair uncited segments using retrieved citation tokens; "
        f"got all_answers_cited={result['all_answers_cited']!r}"
    )
    assert result["citation_fallback_applied"] is False, (
        "citation_fallback_applied must be False when repair succeeds; "
        f"got citation_fallback_applied={result['citation_fallback_applied']!r}"
    )
    cq = result["citation_quality"]
    assert cq["evidence_level"] == "full", (
        f"evidence_level must be 'full' after successful repair; got {cq['evidence_level']!r}"
    )
    # raw_answer preserves the original LLM output unchanged
    assert result["raw_answer"] == uncited_answer, (
        "raw_answer must preserve the original (pre-repair) LLM output"
    )
    # citation_repair_applied must be True when repair fires
    assert result["citation_repair_applied"] is True, (
        "citation_repair_applied must be True when repair fires; "
        f"got citation_repair_applied={result['citation_repair_applied']!r}"
    )
    assert result["citation_repair_strategy"] == "append_first_retrieved_token", (
        "citation_repair_strategy must name the repair algorithm used; "
        f"got {result['citation_repair_strategy']!r}"
    )
    assert result["citation_repair_source_chunk_id"] == "real-chunk-1", (
        "citation_repair_source_chunk_id must be the chunk_id of the repaired hit; "
        f"got {result['citation_repair_source_chunk_id']!r}"
    )
    # raw_answer_all_cited must be False: the original LLM output was NOT fully cited
    assert result["raw_answer_all_cited"] is False, (
        "raw_answer_all_cited must be False when the original LLM output was uncited; "
        f"got raw_answer_all_cited={result['raw_answer_all_cited']!r}"
    )
    # citation_quality must expose raw_answer_all_cited for structured consumers
    assert cq["raw_answer_all_cited"] is False, (
        "citation_quality.raw_answer_all_cited must be False when the original LLM output was uncited"
    )


def test_retrieval_and_qa_live_all_runs_uncited_answer_fallback_when_no_hits(tmp_path: Path):
    """In all_runs mode, the citation fallback must still apply when no hits are retrieved
    (truly insufficient evidence).  No repair is possible without retrieved citation tokens."""
    from demo.stages import run_retrieval_and_qa

    uncited_answer = "Answer without any citation tokens."

    class _FakeRetrieverNoHits:
        def __init__(self, **kwargs):
            pass

        def search(self, **kwargs):
            return _make_fake_retriever_result([])  # No retrieved chunks

    live_config = Config(
        dry_run=False,
        output_dir=tmp_path,
        neo4j_uri="bolt://example.invalid",
        neo4j_username="neo4j",
        neo4j_password="secret",
        neo4j_database="neo4j",
        openai_model="gpt-4o-mini",
    )

    with mock.patch(
        "demo.stages.retrieval_and_qa.VectorCypherRetriever", _FakeRetrieverNoHits
    ), mock.patch(
        "demo.stages.retrieval_and_qa.OpenAIEmbeddings"
    ), mock.patch(
        "demo.stages.retrieval_and_qa.GraphRAG",
        _make_stub_graphrag_class(answer=uncited_answer),
    ), mock.patch(
        "demo.stages.retrieval_and_qa.build_openai_llm"
    ), mock.patch(
        "neo4j.GraphDatabase.driver"
    ), mock.patch.dict(os.environ, {"OPENAI_API_KEY": "test-key"}):
        result = run_retrieval_and_qa(
            live_config,
            run_id=None,
            source_uri=None,
            question="What happened?",
            all_runs=True,
        )

    assert result["citation_fallback_applied"] is True, (
        "citation fallback must apply in all-runs mode when no hits were retrieved; "
        f"got citation_fallback_applied={result['citation_fallback_applied']!r}"
    )
    assert result["all_answers_cited"] is False
    # No repair was possible — citation_repair_applied must be False
    assert result["citation_repair_applied"] is False, (
        "citation_repair_applied must be False when no hits were retrieved; "
        f"got citation_repair_applied={result['citation_repair_applied']!r}"
    )
    assert result["citation_repair_strategy"] is None, (
        "citation_repair_strategy must be None when no repair occurred"
    )
    assert result["citation_repair_source_chunk_id"] is None, (
        "citation_repair_source_chunk_id must be None when no repair occurred"
    )
    assert result["raw_answer_all_cited"] is False, (
        "raw_answer_all_cited must be False when the LLM answer was uncited"
    )


def test_retrieval_and_qa_live_all_runs_fully_cited_answer_no_repair_needed(tmp_path: Path):
    """In all_runs mode, a fully-cited LLM answer must pass through unchanged (no repair
    needed).  all_answers_cited=True, citation_fallback_applied=False, evidence_level='full'."""
    from demo.stages import run_retrieval_and_qa
    from demo.stages.retrieval_and_qa import _build_citation_token

    real_token = _build_citation_token(
        chunk_id="cited-chunk",
        run_id="cited-run",
        source_uri="file:///cited.pdf",
        chunk_index=0,
        page=1,
        start_char=0,
        end_char=50,
    )
    cited_answer = f"Power Atlas spans all ingested runs. {real_token}"

    class _FakeRetrieverCited:
        def __init__(self, **kwargs):
            pass

        def search(self, **kwargs):
            return _make_fake_retriever_result(
                [
                    _make_fake_retriever_result_item(
                        f"Chunk text\n{real_token}",
                        {
                            "citation_token": real_token,
                            "citation_object": {},
                            "chunk_id": "cited-chunk",
                            "run_id": "cited-run",
                            "source_uri": "file:///cited.pdf",
                            "chunk_index": 0,
                            "page": 1,
                            "start_char": 0,
                            "end_char": 50,
                            "score": 0.95,
                            "empty_chunk_text": False,
                        },
                    )
                ]
            )

    live_config = Config(
        dry_run=False,
        output_dir=tmp_path,
        neo4j_uri="bolt://example.invalid",
        neo4j_username="neo4j",
        neo4j_password="secret",
        neo4j_database="neo4j",
        openai_model="gpt-4o-mini",
    )

    with mock.patch(
        "demo.stages.retrieval_and_qa.VectorCypherRetriever", _FakeRetrieverCited
    ), mock.patch(
        "demo.stages.retrieval_and_qa.OpenAIEmbeddings"
    ), mock.patch(
        "demo.stages.retrieval_and_qa.GraphRAG",
        _make_stub_graphrag_class(answer=cited_answer),
    ), mock.patch(
        "demo.stages.retrieval_and_qa.build_openai_llm"
    ), mock.patch(
        "neo4j.GraphDatabase.driver"
    ), mock.patch.dict(os.environ, {"OPENAI_API_KEY": "test-key"}):
        result = run_retrieval_and_qa(
            live_config,
            run_id=None,
            source_uri=None,
            question="What happened?",
            all_runs=True,
        )

    assert result["all_answers_cited"] is True
    assert result["citation_fallback_applied"] is False
    assert result["citation_quality"]["evidence_level"] == "full"
    assert result["raw_answer"] == cited_answer
    # No repair was needed — citation_repair_applied must be False
    assert result["citation_repair_applied"] is False, (
        "citation_repair_applied must be False when the LLM answer was already fully cited"
    )
    assert result["citation_repair_strategy"] is None
    assert result["citation_repair_source_chunk_id"] is None
    # raw_answer was already fully cited — raw_answer_all_cited must be True
    assert result["raw_answer_all_cited"] is True, (
        "raw_answer_all_cited must be True when the original LLM output was fully cited"
    )
    assert result["citation_quality"]["raw_answer_all_cited"] is True, (
        "citation_quality.raw_answer_all_cited must be True when the original LLM output was fully cited"
    )


def test_repair_uncited_answer_appends_token_to_each_uncited_segment():
    """_repair_uncited_answer must append the citation token to each uncited sentence
    and bullet, leaving already-cited segments unchanged."""
    from demo.stages.retrieval_and_qa import _repair_uncited_answer, _check_all_answers_cited

    token = "[CITATION|chunk_id=c1|run_id=r1|source_uri=s1|chunk_index=0|page=1|start_char=0|end_char=10]"

    # Single uncited sentence
    single = "Power was measured at 100 W."
    repaired = _repair_uncited_answer(single, token)
    assert _check_all_answers_cited(repaired), f"Repaired single sentence should be cited: {repaired!r}"

    # Multi-sentence paragraph where second sentence is already cited
    cited_token = "[CITATION|chunk_id=c2|run_id=r2|source_uri=s2|chunk_index=1|page=2|start_char=5|end_char=50]"
    multi = f"First claim. Second claim with citation. {cited_token}"
    repaired_multi = _repair_uncited_answer(multi, token)
    assert _check_all_answers_cited(repaired_multi), (
        f"Repaired multi-sentence answer should be fully cited: {repaired_multi!r}"
    )

    # Bullet list
    bullet_answer = "- Item one uncited\n- Item two also uncited"
    repaired_bullets = _repair_uncited_answer(bullet_answer, token)
    assert _check_all_answers_cited(repaired_bullets), (
        f"Repaired bullet list should be fully cited: {repaired_bullets!r}"
    )

    # Already-cited answer must be returned unchanged
    already_cited = f"Fully cited sentence. {token}"
    result_unchanged = _repair_uncited_answer(already_cited, token)
    assert result_unchanged == already_cited, (
        "Already-cited answer must not be modified by repair"
    )

    # Empty answer must be returned unchanged
    assert _repair_uncited_answer("", token) == ""
    assert _repair_uncited_answer("some text", "") == "some text"


# ---------------------------------------------------------------------------
# citation repair metadata: new fields added for issue observability
# ---------------------------------------------------------------------------

def test_retrieval_and_qa_dry_run_includes_citation_repair_fields(tmp_path: Path):
    """Dry-run result must include citation_repair_applied, citation_repair_strategy, and
    citation_repair_source_chunk_id with their default values (False/None/None)."""
    from demo.stages import run_retrieval_and_qa

    config = _dry_run_config(tmp_path)
    result = run_retrieval_and_qa(config, run_id=None, source_uri=None, all_runs=True)

    assert "citation_repair_applied" in result, (
        "dry-run result must include citation_repair_applied key"
    )
    assert result["citation_repair_applied"] is False
    assert "citation_repair_strategy" in result
    assert result["citation_repair_strategy"] is None
    assert "citation_repair_source_chunk_id" in result
    assert result["citation_repair_source_chunk_id"] is None


def test_retrieval_and_qa_dry_run_includes_raw_answer_all_cited(tmp_path: Path):
    """Dry-run result must include raw_answer_all_cited (False by default) at both the
    top level and inside citation_quality."""
    from demo.stages import run_retrieval_and_qa

    config = _dry_run_config(tmp_path)
    result = run_retrieval_and_qa(config, run_id=None, source_uri=None)

    assert "raw_answer_all_cited" in result, (
        "dry-run result must include raw_answer_all_cited key"
    )
    assert result["raw_answer_all_cited"] is False
    assert "raw_answer_all_cited" in result["citation_quality"], (
        "citation_quality must include raw_answer_all_cited key"
    )
    assert result["citation_quality"]["raw_answer_all_cited"] is False


def test_retrieval_and_qa_live_path_citation_quality_includes_raw_answer_all_cited(
    tmp_path: Path,
):
    """Live path citation_quality must include raw_answer_all_cited when the answer is
    fully cited (True), in addition to all_cited."""
    from demo.stages import run_retrieval_and_qa
    from demo.stages.retrieval_and_qa import _build_citation_token

    real_token = _build_citation_token(
        chunk_id="qa-cq-chunk",
        run_id="qa-cq-run",
        source_uri="file:///qa-cq.pdf",
        chunk_index=0,
        page=1,
        start_char=0,
        end_char=40,
    )
    cited_answer = f"Evidence supports the claim. {real_token}"

    class _FakeRetrieverCQ:
        def __init__(self, **kwargs):
            pass

        def search(self, **kwargs):
            return _make_fake_retriever_result(
                [
                    _make_fake_retriever_result_item(
                        f"Chunk text\n{real_token}",
                        {
                            "citation_token": real_token,
                            "citation_object": {
                                "chunk_id": "qa-cq-chunk",
                                "run_id": "qa-cq-run",
                                "source_uri": "file:///qa-cq.pdf",
                                "chunk_index": 0,
                                "page": 1,
                                "start_char": 0,
                                "end_char": 40,
                            },
                            "chunk_id": "qa-cq-chunk",
                            "run_id": "qa-cq-run",
                            "source_uri": "file:///qa-cq.pdf",
                            "chunk_index": 0,
                            "page": 1,
                            "start_char": 0,
                            "end_char": 40,
                            "score": 0.92,
                            "empty_chunk_text": False,
                        },
                    )
                ]
            )

    live_config = Config(
        dry_run=False,
        output_dir=tmp_path,
        neo4j_uri="bolt://example.invalid",
        neo4j_username="neo4j",
        neo4j_password="secret",
        neo4j_database="neo4j",
        openai_model="gpt-4o-mini",
    )

    with mock.patch(
        "demo.stages.retrieval_and_qa.VectorCypherRetriever", _FakeRetrieverCQ
    ), mock.patch(
        "demo.stages.retrieval_and_qa.OpenAIEmbeddings"
    ), mock.patch(
        "demo.stages.retrieval_and_qa.GraphRAG",
        _make_stub_graphrag_class(answer=cited_answer),
    ), mock.patch(
        "demo.stages.retrieval_and_qa.build_openai_llm"
    ), mock.patch(
        "neo4j.GraphDatabase.driver"
    ), mock.patch.dict(os.environ, {"OPENAI_API_KEY": "test-key"}):
        result = run_retrieval_and_qa(
            live_config,
            run_id="qa-cq-run",
            source_uri=None,
            question="What supports the claim?",
        )

    cq = result["citation_quality"]
    assert "raw_answer_all_cited" in cq, (
        "citation_quality must include raw_answer_all_cited key on the live path"
    )
    assert cq["raw_answer_all_cited"] is True, (
        "citation_quality.raw_answer_all_cited must be True when the original LLM answer was fully cited"
    )
    assert cq["all_cited"] is True
    assert result["raw_answer_all_cited"] is True


def test_retrieval_and_qa_dry_run_all_runs_qa_label(tmp_path: Path):
    """Dry-run result must use 'GraphRAG all-runs citations' label for qa when all_runs=True."""
    from demo.stages import run_retrieval_and_qa

    config = _dry_run_config(tmp_path)
    result = run_retrieval_and_qa(config, run_id=None, source_uri=None, all_runs=True)
    assert result["qa"] == "GraphRAG all-runs citations", (
        f"all_runs=True dry-run must use all-runs qa label; got {result['qa']!r}"
    )


def test_retrieval_and_qa_dry_run_run_scoped_qa_label(tmp_path: Path):
    """Dry-run result must use 'GraphRAG run-scoped citations' label for qa when all_runs=False."""
    from demo.stages import run_retrieval_and_qa

    config = _dry_run_config(tmp_path)
    result = run_retrieval_and_qa(config, run_id="test-run", source_uri=None, all_runs=False)
    assert result["qa"] == "GraphRAG run-scoped citations", (
        f"all_runs=False dry-run must use run-scoped qa label; got {result['qa']!r}"
    )


def test_resolve_ask_scope_run_id_flag(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """--run-id flag must be returned directly and suppress env var override."""
    from demo.run_demo import parse_args, _resolve_ask_scope

    monkeypatch.delenv("UNSTRUCTURED_RUN_ID", raising=False)
    args = parse_args(["--dry-run", "ask", "--run-id", "my-run-123"])
    config = _dry_run_config(tmp_path)
    run_id, all_runs = _resolve_ask_scope(args, config)
    assert run_id == "my-run-123"
    assert all_runs is False


def test_resolve_ask_scope_accepts_request_context(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """The ask-scope helper must accept RequestContext directly for live context-threaded callers."""
    from demo.run_demo import _request_context_from_config, _resolve_ask_scope, parse_args

    monkeypatch.delenv("UNSTRUCTURED_RUN_ID", raising=False)
    args = parse_args(["--dry-run", "ask", "--run-id", "context-run-123"])
    request_context = _request_context_from_config(_dry_run_config(tmp_path), command="ask")

    run_id, all_runs = _resolve_ask_scope(args, request_context)

    assert run_id == "context-run-123"
    assert all_runs is False


def test_prepare_ask_request_context_sets_source_uri(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """Prepared ask request contexts must carry the resolved source_uri for single-run retrieval."""
    from demo.run_demo import _prepare_ask_request_context, _request_context_from_config, parse_args
    from power_atlas.contracts import resolve_dataset_root

    monkeypatch.setenv("FIXTURE_DATASET", "demo_dataset_v1")
    monkeypatch.delenv("UNSTRUCTURED_RUN_ID", raising=False)
    args = parse_args(["--dry-run", "ask", "--run-id", "context-run-456"])
    request_context = _request_context_from_config(_dry_run_config(tmp_path), command="ask")

    prepared = _prepare_ask_request_context(args, request_context)

    assert prepared.run_id == "context-run-456"
    assert prepared.all_runs is False
    assert prepared.source_uri is not None
    assert prepared.source_uri == str(resolve_dataset_root("demo_dataset_v1").pdf_path.resolve().as_uri())


def test_run_retrieval_and_qa_request_context_uses_request_scope(tmp_path: Path):
    """The RequestContext retrieval helper must forward run and source scope directly."""
    from demo.run_demo import _request_context_from_config
    from demo.stages.retrieval_and_qa import run_retrieval_and_qa_request_context

    request_context = _request_context_from_config(
        _dry_run_config(tmp_path),
        command="ask",
        run_id="context-qa-run",
        source_uri="file:///context/doc.pdf",
    )

    result = run_retrieval_and_qa_request_context(request_context)

    assert result["run_id"] == "context-qa-run"
    assert result["source_uri"] == "file:///context/doc.pdf"
    assert result["retrieval_scope"]["run_id"] == "context-qa-run"
    assert result["retrieval_scope"]["source_uri"] == "file:///context/doc.pdf"
    assert result["retriever_index_name"] == request_context.pipeline_contract.chunk_embedding_index_name


def test_run_claim_participation_request_context_uses_request_scope(tmp_path: Path):
    """The RequestContext claim participation helper must forward run and source scope directly."""
    from demo.run_demo import _request_context_from_config
    from demo.stages.claim_participation import run_claim_participation_request_context

    request_context = _request_context_from_config(
        _dry_run_config(tmp_path),
        command="claim-participation",
        run_id="context-participation-run",
        source_uri="file:///context/claim-source.pdf",
    )

    result = run_claim_participation_request_context(request_context)

    assert result["status"] == "dry_run"
    assert result["run_id"] == "context-participation-run"
    assert result["source_uri"] == "file:///context/claim-source.pdf"


def test_run_graph_health_diagnostics_request_context_uses_request_scope(tmp_path: Path):
    """The RequestContext graph-health helper must forward run scope directly."""
    from demo.run_demo import _request_context_from_config
    from demo.stages.graph_health import run_graph_health_diagnostics_request_context

    request_context = _request_context_from_config(
        _dry_run_config(tmp_path),
        command="graph-health",
        run_id="context-graph-health-run",
    )

    result = run_graph_health_diagnostics_request_context(
        request_context,
        alignment_version="v1.0",
    )

    assert result["status"] == "dry_run"
    assert result["run_id"] == "context-graph-health-run"
    assert result["alignment_version"] == "v1.0"


def test_run_retrieval_benchmark_request_context_uses_request_scope(tmp_path: Path):
    """The RequestContext retrieval-benchmark helper must forward run scope and default dataset scope."""
    from demo.run_demo import _request_context_from_config
    from demo.stages.retrieval_benchmark import run_retrieval_benchmark_request_context

    config_data = {**_dry_run_config(tmp_path).__dict__, "dataset_name": "demo_dataset_v1"}
    config = Config(**config_data)
    request_context = _request_context_from_config(
        config,
        command="retrieval-benchmark",
        run_id="context-benchmark-run",
    )

    result = run_retrieval_benchmark_request_context(
        request_context,
        alignment_version="v1.0",
    )

    assert result["status"] == "dry_run"
    assert result["run_id"] == "context-benchmark-run"
    assert result["dataset_id"] == "demo_dataset_v1"
    assert result["alignment_version"] == "v1.0"


def test_resolve_ask_scope_run_id_flag_overrides_env_var(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
):
    """--run-id must override UNSTRUCTURED_RUN_ID and log a warning."""
    from demo.run_demo import parse_args, _resolve_ask_scope

    monkeypatch.setenv("UNSTRUCTURED_RUN_ID", "env-run-id")
    args = parse_args(["--dry-run", "ask", "--run-id", "cli-run-id"])
    config = _dry_run_config(tmp_path)
    with caplog.at_level(logging.WARNING, logger="demo.run_demo"):
        run_id, all_runs = _resolve_ask_scope(args, config)
    assert run_id == "cli-run-id"
    assert all_runs is False
    assert any(
        record.levelno == logging.WARNING
        and "env-run-id" in record.getMessage()
        and "cli-run-id" in record.getMessage()
        for record in caplog.records
    )


def test_resolve_ask_scope_all_runs_flag(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """--all-runs must return all_runs=True."""
    from demo.run_demo import parse_args, _resolve_ask_scope

    monkeypatch.delenv("UNSTRUCTURED_RUN_ID", raising=False)
    args = parse_args(["--dry-run", "ask", "--all-runs"])
    config = _dry_run_config(tmp_path)
    run_id, all_runs = _resolve_ask_scope(args, config)
    assert all_runs is True
    assert run_id is None


def test_resolve_ask_scope_all_runs_overrides_env_var(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
):
    """--all-runs must override UNSTRUCTURED_RUN_ID and log a warning."""
    from demo.run_demo import parse_args, _resolve_ask_scope

    monkeypatch.setenv("UNSTRUCTURED_RUN_ID", "stale-env-run-id")
    args = parse_args(["--dry-run", "ask", "--all-runs"])
    config = _dry_run_config(tmp_path)
    with caplog.at_level(logging.WARNING, logger="demo.run_demo"):
        run_id, all_runs = _resolve_ask_scope(args, config)
    assert all_runs is True
    assert any(
        record.levelno == logging.WARNING and "stale-env-run-id" in record.getMessage()
        for record in caplog.records
    )


def test_resolve_ask_scope_dry_run_uses_env_var(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    """In dry-run default mode, UNSTRUCTURED_RUN_ID must be used as run_id."""
    from demo.run_demo import parse_args, _resolve_ask_scope

    monkeypatch.setenv("UNSTRUCTURED_RUN_ID", "env-run-for-dry")
    args = parse_args(["--dry-run", "ask"])
    config = _dry_run_config(tmp_path)
    run_id, all_runs = _resolve_ask_scope(args, config)
    assert run_id == "env-run-for-dry"
    assert all_runs is False


def test_resolve_ask_scope_dry_run_no_env_var_returns_none(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    """In dry-run default mode with no env var, run_id must be None (gracefully handled)."""
    from demo.run_demo import parse_args, _resolve_ask_scope

    monkeypatch.delenv("UNSTRUCTURED_RUN_ID", raising=False)
    args = parse_args(["--dry-run", "ask"])
    config = _dry_run_config(tmp_path)
    run_id, all_runs = _resolve_ask_scope(args, config)
    assert run_id is None
    assert all_runs is False


def test_main_ask_dry_run_prints_scope_run_id(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture
):
    """main() must print the resolved scope before running ask in non-interactive mode."""
    import sys
    from demo.run_demo import main

    monkeypatch.setenv("FIXTURE_DATASET", "demo_dataset_v1")
    monkeypatch.setenv("UNSTRUCTURED_RUN_ID", "scope-test-run")
    monkeypatch.setattr(
        sys, "argv", ["demo", "--dry-run", "ask", "--run-id", "scope-test-run", f"--output-dir={tmp_path}"]
    )
    main()
    output = capsys.readouterr().out
    assert "Using retrieval scope: run=scope-test-run" in output


def test_main_ask_dry_run_all_runs_prints_scope(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture
):
    """main() must print 'all runs in database' when --all-runs is specified."""
    import sys
    from demo.run_demo import main

    monkeypatch.delenv("UNSTRUCTURED_RUN_ID", raising=False)
    monkeypatch.setattr(
        sys, "argv", ["demo", "--dry-run", "ask", "--all-runs", f"--output-dir={tmp_path}"]
    )
    main()
    output = capsys.readouterr().out
    assert "Using retrieval scope: all runs in database" in output


def test_main_ask_dry_run_no_scope_prints_placeholder(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture
):
    """main() must print a placeholder scope label when no scope is set in dry-run mode."""
    import sys
    from demo.run_demo import main

    monkeypatch.setenv("FIXTURE_DATASET", "demo_dataset_v1")
    monkeypatch.delenv("UNSTRUCTURED_RUN_ID", raising=False)
    monkeypatch.setattr(
        sys, "argv", ["demo", "--dry-run", "ask", f"--output-dir={tmp_path}"]
    )
    main()
    output = capsys.readouterr().out
    # The output should mention the scope, even as a placeholder
    assert "Using retrieval scope:" in output


def test_run_interactive_qa_all_runs_prints_scope(
    tmp_path: Path, capsys: pytest.CaptureFixture
):
    """run_interactive_qa with all_runs=True must print 'all runs in database' scope message."""
    from demo.stages.retrieval_and_qa import run_interactive_qa

    live_config = Config(
        dry_run=False,
        output_dir=tmp_path,
        neo4j_uri="bolt://example.invalid",
        neo4j_username="neo4j",
        neo4j_password="secret",
        neo4j_database="neo4j",
        openai_model="gpt-4o-mini",
    )

    class _FakeRetriever:
        def __init__(self, **kwargs):
            pass

        def search(self, **kwargs):
            return _make_fake_retriever_result([])

    with mock.patch("demo.stages.retrieval_and_qa.VectorCypherRetriever", _FakeRetriever), mock.patch(
        "demo.stages.retrieval_and_qa.OpenAIEmbeddings"
    ), mock.patch(
        "demo.stages.retrieval_and_qa.GraphRAG", _make_stub_graphrag_class()
    ), mock.patch(
        "demo.stages.retrieval_and_qa.build_openai_llm"
    ), mock.patch(
        "neo4j.GraphDatabase.driver"
    ), mock.patch.dict(os.environ, {"OPENAI_API_KEY": "test-key"}), mock.patch(
        "builtins.input", side_effect=EOFError
    ):
        run_interactive_qa(live_config, run_id=None, all_runs=True)

    output = capsys.readouterr().out
    assert "all runs in database" in output


def test_run_interactive_qa_run_scoped_prints_scope(
    tmp_path: Path, capsys: pytest.CaptureFixture
):
    """run_interactive_qa must print the run_id scope message at session start."""
    from demo.stages.retrieval_and_qa import run_interactive_qa

    live_config = Config(
        dry_run=False,
        output_dir=tmp_path,
        neo4j_uri="bolt://example.invalid",
        neo4j_username="neo4j",
        neo4j_password="secret",
        neo4j_database="neo4j",
        openai_model="gpt-4o-mini",
    )

    class _FakeRetriever:
        def __init__(self, **kwargs):
            pass

        def search(self, **kwargs):
            return _make_fake_retriever_result([])

    with mock.patch("demo.stages.retrieval_and_qa.VectorCypherRetriever", _FakeRetriever), mock.patch(
        "demo.stages.retrieval_and_qa.OpenAIEmbeddings"
    ), mock.patch(
        "demo.stages.retrieval_and_qa.GraphRAG", _make_stub_graphrag_class()
    ), mock.patch(
        "demo.stages.retrieval_and_qa.build_openai_llm"
    ), mock.patch(
        "neo4j.GraphDatabase.driver"
    ), mock.patch.dict(os.environ, {"OPENAI_API_KEY": "test-key"}), mock.patch(
        "builtins.input", side_effect=EOFError
    ):
        run_interactive_qa(live_config, run_id="interactive-scope-run")

    output = capsys.readouterr().out
    assert "Using retrieval scope: run=interactive-scope-run" in output


def test_run_interactive_qa_requires_run_id_when_not_all_runs(tmp_path: Path):
    """run_interactive_qa must raise ValueError when run_id is None and all_runs is False."""
    from demo.stages.retrieval_and_qa import run_interactive_qa

    live_config = Config(
        dry_run=False,
        output_dir=tmp_path,
        neo4j_uri="bolt://example.invalid",
        neo4j_username="neo4j",
        neo4j_password="secret",
        neo4j_database="neo4j",
        openai_model="gpt-4o-mini",
    )
    with mock.patch.dict(os.environ, {"OPENAI_API_KEY": "test-key"}):
        with pytest.raises(ValueError, match="run_id is required"):
            run_interactive_qa(live_config, run_id=None, all_runs=False)


def test_run_retrieval_and_qa_all_runs_uses_unscoped_retrieval_query_contract(tmp_path: Path):
    """retrieval_query_contract in the result must not contain '$run_id' when all_runs=True."""
    from demo.stages import run_retrieval_and_qa

    config = _dry_run_config(tmp_path)
    result = run_retrieval_and_qa(config, run_id=None, source_uri=None, all_runs=True)
    contract = result.get("retrieval_query_contract", "")
    assert "$run_id" not in contract, (
        f"all_runs=True retrieval_query_contract must not filter by $run_id, got:\n{contract}"
    )


def test_run_retrieval_and_qa_run_scoped_uses_run_id_in_query_contract(tmp_path: Path):
    """retrieval_query_contract must contain '$run_id' for run-scoped (non-all_runs) mode."""
    from demo.stages import run_retrieval_and_qa

    config = _dry_run_config(tmp_path)
    result = run_retrieval_and_qa(config, run_id="qa-run-contract", source_uri=None, all_runs=False)
    contract = result.get("retrieval_query_contract", "")
    assert "$run_id" in contract, (
        f"run-scoped retrieval_query_contract must filter by $run_id, got:\n{contract}"
    )


def test_ask_interactive_rejects_dry_run_still_works(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    """Regression: CLI 'ask --interactive' must still raise SystemExit when config.dry_run=True.
    This behavior must not be broken by the new scope resolution changes."""
    import sys
    from demo.run_demo import main

    monkeypatch.setenv("UNSTRUCTURED_RUN_ID", "test-run-id")
    monkeypatch.setattr(sys, "argv", ["demo", "--dry-run", "ask", "--interactive"])
    with pytest.raises(SystemExit) as exc_info:
        main()
    assert "live" in str(exc_info.value).lower() or exc_info.value.code not in (0, None)


# ---------------------------------------------------------------------------
# ask --all-runs manifest: run_id must not be "all_runs" sentinel
# ---------------------------------------------------------------------------

def test_ask_all_runs_manifest_run_id_is_not_sentinel(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    """ask --all-runs manifest top-level run_id must not be the 'all_runs' sentinel string."""
    import sys
    from demo.run_demo import main

    monkeypatch.delenv("UNSTRUCTURED_RUN_ID", raising=False)
    monkeypatch.setattr(
        sys, "argv", ["demo", "--dry-run", "ask", "--all-runs", f"--output-dir={tmp_path}"]
    )
    main()
    import json
    # The manifest path sits under runs/<run_id>/retrieval_and_qa/manifest.json
    manifests = list(tmp_path.glob("runs/*/retrieval_and_qa/manifest.json"))
    assert len(manifests) == 1, f"Expected exactly one ask manifest, found: {manifests}"
    manifest = json.loads(manifests[0].read_text(encoding="utf-8"))
    assert manifest["run_id"] != "all_runs", (
        "ask --all-runs must not use 'all_runs' as a fake ingest run id; "
        f"got run_id={manifest['run_id']!r}"
    )
    assert manifest["run_id"].startswith("ask-"), (
        f"ask --all-runs run_id should start with 'ask-', got: {manifest['run_id']!r}"
    )


def test_ask_all_runs_manifest_unstructured_run_id_is_null(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    """ask --all-runs manifest run_scopes.unstructured_ingest_run_id must be null, not 'all_runs'."""
    import sys
    from demo.run_demo import main

    monkeypatch.delenv("UNSTRUCTURED_RUN_ID", raising=False)
    monkeypatch.setattr(
        sys, "argv", ["demo", "--dry-run", "ask", "--all-runs", f"--output-dir={tmp_path}"]
    )
    main()
    import json
    manifests = list(tmp_path.glob("runs/*/retrieval_and_qa/manifest.json"))
    assert len(manifests) == 1, f"Expected exactly one ask manifest, found: {manifests}"
    manifest = json.loads(manifests[0].read_text(encoding="utf-8"))
    run_scopes = manifest.get("run_scopes", {})
    assert run_scopes.get("unstructured_ingest_run_id") is None, (
        "ask --all-runs must not store a fake ingest run id; "
        f"run_scopes.unstructured_ingest_run_id={run_scopes.get('unstructured_ingest_run_id')!r}"
    )
    # batch_mode must still be present to identify this as a single independent run
    assert run_scopes.get("batch_mode") == "single_independent_run"


def test_ask_run_scoped_manifest_unstructured_run_id_is_set(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    """ask with an explicit run_id must store it in run_scopes.unstructured_ingest_run_id."""
    import sys
    from demo.run_demo import main

    monkeypatch.setenv("FIXTURE_DATASET", "demo_dataset_v1")
    monkeypatch.setenv("UNSTRUCTURED_RUN_ID", "unstructured_ingest-20260101T000000000000Z-aabbccdd")
    monkeypatch.setattr(
        sys, "argv", ["demo", "--dry-run", "ask", f"--output-dir={tmp_path}"]
    )
    main()
    import json
    manifests = list(tmp_path.glob("runs/*/retrieval_and_qa/manifest.json"))
    assert len(manifests) == 1, f"Expected exactly one ask manifest, found: {manifests}"
    manifest = json.loads(manifests[0].read_text(encoding="utf-8"))
    run_scopes = manifest.get("run_scopes", {})
    assert run_scopes.get("unstructured_ingest_run_id") == "unstructured_ingest-20260101T000000000000Z-aabbccdd"


# ---------------------------------------------------------------------------
# Claim participation edge tests — _format_claim_details and _chunk_citation_formatter
# ---------------------------------------------------------------------------

def test_chunk_citation_formatter_includes_claim_details_in_content_with_subject_and_object():
    """_chunk_citation_formatter must include claim details in content when claim_details
    contains entries with explicit subject/object mention data (HAS_SUBJECT/HAS_OBJECT edges)."""
    from demo.stages.retrieval_and_qa import _chunk_citation_formatter

    record = _make_fake_neo4j_record(
        chunk_id="c-cd-1",
        run_id="r1",
        source_uri="file:///doc.pdf",
        chunk_index=0,
        page=1,
        start_char=0,
        end_char=200,
        chunk_text="Marcos Galperin founded MercadoLibre.",
        similarityScore=0.95,
        claims=["Marcos Galperin founded MercadoLibre."],
        claim_details=[
            {
                "claim_text": "Marcos Galperin founded MercadoLibre.",
                "subject_mention": {"name": "Marcos Galperin", "match_method": "raw_exact"},
                "object_mention": {"name": "MercadoLibre", "match_method": "raw_exact"},
            }
        ],
    )
    item = _chunk_citation_formatter(record)
    assert "Marcos Galperin founded MercadoLibre." in item.content
    assert "[Claim context" in item.content
    assert "subject='Marcos Galperin'" in item.content
    assert "object='MercadoLibre'" in item.content
    assert "raw_exact" in item.content
    # Citation token must still be present at the end
    assert "[CITATION|" in item.content


def test_chunk_citation_formatter_claim_details_stored_in_metadata():
    """_chunk_citation_formatter must store claim_details in metadata when present so
    downstream consumers can inspect participation edge data programmatically."""
    from demo.stages.retrieval_and_qa import _chunk_citation_formatter

    claim_details_data = [
        {
            "claim_text": "Endeavor invested in MercadoLibre.",
            "subject_mention": {"name": "Endeavor", "match_method": "casefold_exact"},
            "object_mention": {"name": "MercadoLibre", "match_method": "raw_exact"},
        }
    ]
    record = _make_fake_neo4j_record(
        chunk_id="c-cd-2",
        run_id="r2",
        source_uri="file:///doc.pdf",
        chunk_index=1,
        page=2,
        start_char=0,
        end_char=100,
        chunk_text="Endeavor invested in MercadoLibre.",
        similarityScore=0.88,
        claims=["Endeavor invested in MercadoLibre."],
        claim_details=claim_details_data,
    )
    item = _chunk_citation_formatter(record)
    assert "claim_details" in item.metadata, (
        "claim_details must be stored in metadata when claim_details field is present in the record"
    )
    assert item.metadata["claim_details"] == claim_details_data, (
        "claim_details in metadata must equal the structured participation edge data"
    )


def test_chunk_citation_formatter_claim_details_absent_when_field_missing():
    """_chunk_citation_formatter must not include claim_details in metadata or content when
    the record does not have a claim_details field (base or non-expanded retrieval query)."""
    from demo.stages.retrieval_and_qa import _chunk_citation_formatter

    record = _make_fake_neo4j_record(
        chunk_id="c-cd-3",
        run_id="r3",
        source_uri="file:///doc.pdf",
        chunk_index=2,
        page=3,
        start_char=0,
        end_char=100,
        chunk_text="Some text without claim details.",
        similarityScore=0.75,
        # No claim_details key — simulates base retrieval query
    )
    item = _chunk_citation_formatter(record)
    assert "claim_details" not in item.metadata, (
        "claim_details must not appear in metadata when the record has no claim_details field"
    )
    assert "[Claim context" not in item.content, (
        "Claim context section must not appear in content when claim_details is absent"
    )


def test_chunk_citation_formatter_claim_details_no_participation_edges():
    """_chunk_citation_formatter must handle claims with no participation edges gracefully.
    When subject_mention and object_mention are both None, the claim text still appears
    but without role annotations — no chunk co-location fallback is used."""
    from demo.stages.retrieval_and_qa import _chunk_citation_formatter

    record = _make_fake_neo4j_record(
        chunk_id="c-cd-4",
        run_id="r4",
        source_uri="file:///doc.pdf",
        chunk_index=0,
        page=1,
        start_char=0,
        end_char=100,
        chunk_text="An unresolved claim appeared here.",
        similarityScore=0.70,
        claims=["An unresolved claim appeared here."],
        claim_details=[
            {
                "claim_text": "An unresolved claim appeared here.",
                "subject_mention": None,
                "object_mention": None,
            }
        ],
    )
    item = _chunk_citation_formatter(record)
    # Claim text must appear in the claim context section
    assert "An unresolved claim appeared here." in item.content
    assert "[Claim context" in item.content
    # But no subject/object role annotations
    assert "subject=" not in item.content
    assert "object=" not in item.content
    # Citation token still present
    assert "[CITATION|" in item.content


def test_chunk_citation_formatter_claim_details_only_subject_mention():
    """_chunk_citation_formatter must handle claims with only a subject participation edge
    (no object edge) — only the subject role is annotated."""
    from demo.stages.retrieval_and_qa import _chunk_citation_formatter

    record = _make_fake_neo4j_record(
        chunk_id="c-cd-5",
        run_id="r5",
        source_uri="file:///doc.pdf",
        chunk_index=0,
        page=1,
        start_char=0,
        end_char=150,
        chunk_text="Galperin leads strategy.",
        similarityScore=0.82,
        claims=["Galperin leads strategy."],
        claim_details=[
            {
                "claim_text": "Galperin leads strategy.",
                "subject_mention": {"name": "Galperin", "match_method": "normalized_exact"},
                "object_mention": None,
            }
        ],
    )
    item = _chunk_citation_formatter(record)
    assert "subject='Galperin'" in item.content
    assert "object=" not in item.content
    assert "normalized_exact" in item.content


def test_chunk_citation_formatter_claim_details_and_cluster_context_both_present():
    """When both claim_details and cluster context are present, both sections must appear
    in the content in the order: chunk text → claim context → cluster context → citation."""
    from demo.stages.retrieval_and_qa import _chunk_citation_formatter

    record = _make_fake_neo4j_record(
        chunk_id="c-cd-6",
        run_id="r6",
        source_uri="file:///doc.pdf",
        chunk_index=0,
        page=1,
        start_char=0,
        end_char=200,
        chunk_text="Entity X acquired Company Y.",
        similarityScore=0.91,
        claims=["Entity X acquired Company Y."],
        claim_details=[
            {
                "claim_text": "Entity X acquired Company Y.",
                "subject_mention": {"name": "Entity X", "match_method": "raw_exact"},
                "object_mention": {"name": "Company Y", "match_method": "casefold_exact"},
            }
        ],
        cluster_memberships=[
            {"cluster_name": "Entity X Corp", "membership_status": "provisional", "membership_method": "fuzzy"},
        ],
        cluster_canonical_alignments=[],
    )
    item = _chunk_citation_formatter(record)
    assert "Entity X acquired Company Y." in item.content
    assert "[Claim context" in item.content
    assert "subject='Entity X'" in item.content
    assert "[Cluster context" in item.content
    assert "PROVISIONAL CLUSTER" in item.content
    # Claim context must appear before cluster context
    claim_pos = item.content.index("[Claim context")
    cluster_pos = item.content.index("[Cluster context")
    assert claim_pos < cluster_pos, (
        "Claim context section must appear before cluster context section in content"
    )
    assert "[CITATION|" in item.content


def test_chunk_citation_formatter_arbitrary_roles_in_content():
    """_chunk_citation_formatter must render arbitrary roles (e.g. agent, target) from the
    new ``roles`` list format in content so the LLM sees all participation edges."""
    from demo.stages.retrieval_and_qa import _chunk_citation_formatter

    record = _make_fake_neo4j_record(
        chunk_id="c-cd-7",
        run_id="r7",
        source_uri="file:///doc.pdf",
        chunk_index=0,
        page=1,
        start_char=0,
        end_char=200,
        chunk_text="The board authorised the acquisition.",
        similarityScore=0.87,
        claims=["The board authorised the acquisition."],
        claim_details=[
            {
                "claim_text": "The board authorised the acquisition.",
                "roles": [
                    {"role": "agent", "name": "The board", "match_method": "casefold_exact"},
                    {"role": "target", "name": "the acquisition", "match_method": "normalized_exact"},
                ],
            }
        ],
    )
    item = _chunk_citation_formatter(record)
    assert "[Claim context" in item.content
    assert "agent='The board'" in item.content
    assert "target='the acquisition'" in item.content
    assert "[CITATION|" in item.content



def test_retrieval_query_with_expansion_includes_claim_details_field():
    """_RETRIEVAL_QUERY_WITH_EXPANSION must contain claim_details as a pattern comprehension
    that traverses all HAS_PARTICIPANT edges and collects roles generically."""
    from demo.stages.retrieval_and_qa import _RETRIEVAL_QUERY_WITH_EXPANSION

    assert "claim_details" in _RETRIEVAL_QUERY_WITH_EXPANSION, (
        "_RETRIEVAL_QUERY_WITH_EXPANSION must return a claim_details field for participation edge data"
    )
    assert "HAS_PARTICIPANT" in _RETRIEVAL_QUERY_WITH_EXPANSION, (
        "_RETRIEVAL_QUERY_WITH_EXPANSION must traverse HAS_PARTICIPANT edges"
    )
    assert "r.role" in _RETRIEVAL_QUERY_WITH_EXPANSION, (
        "_RETRIEVAL_QUERY_WITH_EXPANSION must collect r.role generically for all participation edges"
    )
    assert "match_method" in _RETRIEVAL_QUERY_WITH_EXPANSION, (
        "_RETRIEVAL_QUERY_WITH_EXPANSION must include match_method in claim_details"
    )


def test_retrieval_query_with_cluster_includes_claim_details_field():
    """_RETRIEVAL_QUERY_WITH_CLUSTER must contain claim_details with HAS_PARTICIPANT edges."""
    from demo.stages.retrieval_and_qa import _RETRIEVAL_QUERY_WITH_CLUSTER

    assert "claim_details" in _RETRIEVAL_QUERY_WITH_CLUSTER
    assert "HAS_PARTICIPANT" in _RETRIEVAL_QUERY_WITH_CLUSTER
    assert "r.role" in _RETRIEVAL_QUERY_WITH_CLUSTER


def test_retrieval_query_all_runs_variants_include_claim_details_field():
    """Both all-runs graph-expanded queries must include claim_details for participation edges."""
    from demo.stages.retrieval_and_qa import (
        _RETRIEVAL_QUERY_WITH_EXPANSION_ALL_RUNS,
        _RETRIEVAL_QUERY_WITH_CLUSTER_ALL_RUNS,
    )

    for name, query in [
        ("_RETRIEVAL_QUERY_WITH_EXPANSION_ALL_RUNS", _RETRIEVAL_QUERY_WITH_EXPANSION_ALL_RUNS),
        ("_RETRIEVAL_QUERY_WITH_CLUSTER_ALL_RUNS", _RETRIEVAL_QUERY_WITH_CLUSTER_ALL_RUNS),
    ]:
        assert "claim_details" in query, f"{name} must return claim_details"
        assert "HAS_PARTICIPANT" in query, f"{name} must traverse HAS_PARTICIPANT edges"
        assert "r.role" in query, f"{name} must collect r.role generically"


def test_format_claim_details_empty_returns_empty_string():
    """_format_claim_details must return an empty string for an empty list."""
    from demo.stages.retrieval_and_qa import _format_claim_details

    assert _format_claim_details([]) == ""


def test_format_claim_details_renders_subject_and_object():
    """_format_claim_details must render claim text with both subject and object annotations."""
    from demo.stages.retrieval_and_qa import _format_claim_details

    details = [
        {
            "claim_text": "Galperin co-founded MercadoLibre.",
            "subject_mention": {"name": "Galperin", "match_method": "raw_exact"},
            "object_mention": {"name": "MercadoLibre", "match_method": "raw_exact"},
        }
    ]
    result = _format_claim_details(details)
    assert "[Claim context" in result
    assert "Galperin co-founded MercadoLibre." in result
    assert "subject='Galperin'" in result
    assert "object='MercadoLibre'" in result
    assert "raw_exact" in result


def test_format_claim_details_no_participation_edges_renders_claim_text_only():
    """_format_claim_details must render the claim text without role annotations when
    no participation edges exist (subject_mention and object_mention are both None)."""
    from demo.stages.retrieval_and_qa import _format_claim_details

    details = [
        {
            "claim_text": "Company Z expanded overseas.",
            "subject_mention": None,
            "object_mention": None,
        }
    ]
    result = _format_claim_details(details)
    assert "Company Z expanded overseas." in result
    assert "subject=" not in result
    assert "object=" not in result


def test_format_claim_details_new_format_subject_and_object():
    """_format_claim_details must render subject and object annotations from the new
    ``roles`` list format (generic HAS_PARTICIPANT collection), preserving current output."""
    from demo.stages.retrieval_and_qa import _format_claim_details

    details = [
        {
            "claim_text": "Galperin co-founded MercadoLibre.",
            "roles": [
                {"role": "subject", "name": "Galperin", "match_method": "raw_exact"},
                {"role": "object", "name": "MercadoLibre", "match_method": "raw_exact"},
            ],
        }
    ]
    result = _format_claim_details(details)
    assert "[Claim context" in result
    assert "Galperin co-founded MercadoLibre." in result
    assert "subject='Galperin'" in result
    assert "object='MercadoLibre'" in result
    assert "raw_exact" in result


def test_format_claim_details_new_format_arbitrary_roles():
    """_format_claim_details must render arbitrary roles (e.g. agent, target) from the
    new ``roles`` list format without requiring code changes for each new role."""
    from demo.stages.retrieval_and_qa import _format_claim_details

    details = [
        {
            "claim_text": "The board authorised the acquisition.",
            "roles": [
                {"role": "agent", "name": "The board", "match_method": "casefold_exact"},
                {"role": "target", "name": "the acquisition", "match_method": "normalized_exact"},
            ],
        }
    ]
    result = _format_claim_details(details)
    assert "[Claim context" in result
    assert "The board authorised the acquisition." in result
    assert "agent='The board'" in result
    assert "target='the acquisition'" in result
    assert "casefold_exact" in result
    assert "normalized_exact" in result


def test_format_claim_details_new_format_mixed_roles():
    """_format_claim_details must render a mix of subject/object and additional roles
    (e.g. agent) correctly when they appear together in the roles list."""
    from demo.stages.retrieval_and_qa import _format_claim_details

    details = [
        {
            "claim_text": "Smith, acting as agent, transferred assets to Corp.",
            "roles": [
                {"role": "subject", "name": "assets", "match_method": "raw_exact"},
                {"role": "object", "name": "Corp", "match_method": "raw_exact"},
                {"role": "agent", "name": "Smith", "match_method": "casefold_exact"},
            ],
        }
    ]
    result = _format_claim_details(details)
    assert "subject='assets'" in result
    assert "object='Corp'" in result
    assert "agent='Smith'" in result


def test_format_claim_details_new_format_empty_roles_list():
    """_format_claim_details must render claim text without role annotations when the
    new ``roles`` list is present but empty (no resolved participation edges)."""
    from demo.stages.retrieval_and_qa import _format_claim_details

    details = [
        {
            "claim_text": "An unresolved claim.",
            "roles": [],
        }
    ]
    result = _format_claim_details(details)
    assert "An unresolved claim." in result
    assert "[Claim context" in result
    assert "=" not in result.split("An unresolved claim.")[1].split("\n")[0]


def test_retrieval_and_qa_expand_graph_surfaces_claim_details_in_metadata(tmp_path: Path):
    """Expand-graph retrieval must surface claim_details (with subject/object mention data)
    in retrieval_results metadata, confirming that participation edges are included in the
    retrieved context layer so downstream consumers can inspect role assignments."""
    from demo.stages import run_retrieval_and_qa
    from demo.stages.retrieval_and_qa import _chunk_citation_formatter

    claim_details_data = [
        {
            "claim_text": "Galperin founded MercadoLibre.",
            "subject_mention": {"name": "Galperin", "match_method": "raw_exact"},
            "object_mention": {"name": "MercadoLibre", "match_method": "raw_exact"},
        }
    ]
    record = _make_fake_neo4j_record(
        chunk_id="chunk-cd-e2e",
        run_id="expand-run",
        source_uri="file:///evidence.pdf",
        chunk_index=0,
        page=1,
        start_char=0,
        end_char=100,
        chunk_text="Galperin founded MercadoLibre.",
        similarityScore=0.93,
        claims=["Galperin founded MercadoLibre."],
        mentions=["Galperin", "MercadoLibre"],
        canonical_entities=[],
        claim_details=claim_details_data,
    )
    item = _chunk_citation_formatter(record)

    class _FakeRetriever:
        def __init__(self, **kwargs):
            pass

        def search(self, **kwargs):
            return _make_fake_retriever_result([item])

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
        "demo.stages.retrieval_and_qa.build_openai_llm"
    ), mock.patch("neo4j.GraphDatabase.driver"), mock.patch.dict(os.environ, {"OPENAI_API_KEY": "test-key"}):
        result = run_retrieval_and_qa(
            live_config,
            run_id="expand-run",
            source_uri=None,
            question="Who founded MercadoLibre?",
            expand_graph=True,
        )

    assert result["status"] == "live"
    assert result["hits"] == 1
    hit_meta = result["retrieval_results"][0]["metadata"]
    assert "claim_details" in hit_meta, (
        "expand_graph retrieval results must include claim_details in metadata"
    )
    assert hit_meta["claim_details"] == claim_details_data, (
        "claim_details in metadata must contain subject/object mention data from participation edges"
    )
    # Content must include the claim context section
    hit_content = result["retrieval_results"][0]["content"]
    assert "subject='Galperin'" in hit_content, (
        "claim subject mention must appear in retrieved content for expand_graph mode"
    )
    assert "object='MercadoLibre'" in hit_content, (
        "claim object mention must appear in retrieved content for expand_graph mode"
    )


# ---------------------------------------------------------------------------
# Run-scoping: query string structural tests
# ---------------------------------------------------------------------------


def _normalize_query(query: str) -> str:
    """Collapse all whitespace sequences in a Cypher query to a single space.

    Structural tests use substring assertions against query constants.  Normalizing
    whitespace first makes those assertions resilient to harmless formatting changes
    (re-indentation, line wrapping) so a test only fails on a genuine semantic regression.
    """
    return " ".join(query.split())


def test_retrieval_query_with_expansion_run_scopes_chunk_claim_and_mention():
    """_RETRIEVAL_QUERY_WITH_EXPANSION must filter chunk, claim, and mention nodes by run_id.

    Run scoping is preserved across all graph traversal targets: the chunk node itself
    (c.run_id = $run_id), claims backed by SUPPORTED_BY (claim.run_id = $run_id), and
    entity mentions reached via MENTIONED_IN (mention.run_id = $run_id).  Without these
    guards a run-scoped query can surface data from neighbouring ingestion runs.
    """
    from demo.stages.retrieval_and_qa import _RETRIEVAL_QUERY_WITH_EXPANSION

    q = _normalize_query(_RETRIEVAL_QUERY_WITH_EXPANSION)
    assert "c.run_id = $run_id" in q, (
        "_RETRIEVAL_QUERY_WITH_EXPANSION must filter the chunk node by c.run_id = $run_id"
    )
    assert "claim.run_id = $run_id" in q, (
        "_RETRIEVAL_QUERY_WITH_EXPANSION must filter ExtractedClaim nodes by claim.run_id = $run_id"
    )
    assert "mention.run_id = $run_id" in q, (
        "_RETRIEVAL_QUERY_WITH_EXPANSION must filter EntityMention nodes by mention.run_id = $run_id"
    )


def test_retrieval_query_with_cluster_run_scopes_chunk_claim_mention_and_alignment():
    """_RETRIEVAL_QUERY_WITH_CLUSTER must filter chunk, claim, mention, and ALIGNED_WITH by run_id.

    In addition to chunk/claim/mention scoping, the ALIGNED_WITH edge filter must include
    both a.run_id = $run_id and a.alignment_version = $alignment_version to prevent
    mixed-version or cross-run alignment contamination.
    """
    from demo.stages.retrieval_and_qa import _RETRIEVAL_QUERY_WITH_CLUSTER

    q = _normalize_query(_RETRIEVAL_QUERY_WITH_CLUSTER)
    assert "c.run_id = $run_id" in q, (
        "_RETRIEVAL_QUERY_WITH_CLUSTER must filter the chunk node by c.run_id = $run_id"
    )
    assert "claim.run_id = $run_id" in q, (
        "_RETRIEVAL_QUERY_WITH_CLUSTER must filter ExtractedClaim nodes by claim.run_id = $run_id"
    )
    assert "mention.run_id = $run_id" in q, (
        "_RETRIEVAL_QUERY_WITH_CLUSTER must filter EntityMention nodes by mention.run_id = $run_id"
    )
    assert "a.run_id = $run_id" in q, (
        "_RETRIEVAL_QUERY_WITH_CLUSTER must filter ALIGNED_WITH edges by a.run_id = $run_id"
    )
    assert "a.alignment_version = $alignment_version" in q, (
        "_RETRIEVAL_QUERY_WITH_CLUSTER must filter ALIGNED_WITH by a.alignment_version = $alignment_version"
    )


def test_retrieval_query_all_runs_variants_omit_run_id_filter():
    """All-runs query variants must NOT contain $run_id parameter references.

    When all_runs=True the retriever intentionally queries across all ingestion runs.
    Any accidental $run_id reference in the query body would silently scope results to
    a single run (or fail at execution when run_id is None).
    """
    from demo.stages.retrieval_and_qa import (
        _RETRIEVAL_QUERY_BASE_ALL_RUNS,
        _RETRIEVAL_QUERY_WITH_EXPANSION_ALL_RUNS,
    )

    for name, query in [
        ("_RETRIEVAL_QUERY_BASE_ALL_RUNS", _RETRIEVAL_QUERY_BASE_ALL_RUNS),
        ("_RETRIEVAL_QUERY_WITH_EXPANSION_ALL_RUNS", _RETRIEVAL_QUERY_WITH_EXPANSION_ALL_RUNS),
    ]:
        assert "$run_id" not in _normalize_query(query), (
            f"{name} must not reference $run_id — all-runs queries must not filter by run"
        )


def test_retrieval_query_with_cluster_all_runs_uses_per_chunk_run_id_for_alignment():
    """_RETRIEVAL_QUERY_WITH_CLUSTER_ALL_RUNS must scope ALIGNED_WITH by the mention's own run_id.

    In all-runs mode there is no global $run_id parameter.  The ALIGNED_WITH filter must
    use a.run_id = mention.run_id (each chunk's local run) rather than $run_id so that
    alignment edges are matched against the correct provenance for each individual hit.
    The alignment_version parameter is still scoped globally via $alignment_version.
    """
    from demo.stages.retrieval_and_qa import _RETRIEVAL_QUERY_WITH_CLUSTER_ALL_RUNS

    q = _normalize_query(_RETRIEVAL_QUERY_WITH_CLUSTER_ALL_RUNS)
    assert "$run_id" not in q, (
        "_RETRIEVAL_QUERY_WITH_CLUSTER_ALL_RUNS must not use global $run_id filter"
    )
    assert "a.run_id = mention.run_id" in q, (
        "_RETRIEVAL_QUERY_WITH_CLUSTER_ALL_RUNS must scope ALIGNED_WITH via a.run_id = mention.run_id "
        "so each hit uses its own run provenance"
    )
    assert "a.alignment_version = $alignment_version" in q, (
        "_RETRIEVAL_QUERY_WITH_CLUSTER_ALL_RUNS must still filter ALIGNED_WITH by $alignment_version"
    )


# ---------------------------------------------------------------------------
# All-runs mode: per-hit run_id provenance in citation metadata
# ---------------------------------------------------------------------------


def test_all_runs_retrieve_preserves_per_hit_run_id_in_metadata(tmp_path: Path):
    """In all_runs mode, each hit's citation metadata must preserve the run_id from the
    underlying chunk record so consumers can trace the provenance of individual results
    across multiple ingestion runs.

    Cross-run retrieval is only meaningful if each hit remains traceable to its source
    run — a hit without a run_id in metadata cannot be attributed to a specific ingest.
    """
    from demo.stages import run_retrieval_and_qa
    from demo.stages.retrieval_and_qa import _chunk_citation_formatter

    run_a_record = _make_fake_neo4j_record(
        chunk_id="chunk-run-a",
        run_id="ingest-run-a",
        source_uri="file:///doc-a.pdf",
        chunk_index=0,
        page=1,
        start_char=0,
        end_char=100,
        chunk_text="Content from run A.",
        similarityScore=0.92,
    )
    run_b_record = _make_fake_neo4j_record(
        chunk_id="chunk-run-b",
        run_id="ingest-run-b",
        source_uri="file:///doc-b.pdf",
        chunk_index=0,
        page=1,
        start_char=0,
        end_char=100,
        chunk_text="Content from run B.",
        similarityScore=0.87,
    )
    item_a = _chunk_citation_formatter(run_a_record)
    item_b = _chunk_citation_formatter(run_b_record)

    class _FakeRetriever:
        def __init__(self, **kwargs):
            pass

        def search(self, **kwargs):
            return _make_fake_retriever_result([item_a, item_b])

    live_config = Config(
        dry_run=False,
        output_dir=tmp_path,
        neo4j_uri="bolt://example.invalid",
        neo4j_username="neo4j",
        neo4j_password="secret",
        neo4j_database="neo4j",
        openai_model="gpt-4o-mini",
    )

    with mock.patch("demo.stages.retrieval_and_qa.VectorCypherRetriever", _FakeRetriever), mock.patch(
        "demo.stages.retrieval_and_qa.OpenAIEmbeddings"
    ), mock.patch(
        "demo.stages.retrieval_and_qa.GraphRAG", _make_stub_graphrag_class()
    ), mock.patch(
        "demo.stages.retrieval_and_qa.build_openai_llm"
    ), mock.patch("neo4j.GraphDatabase.driver"), mock.patch.dict(os.environ, {"OPENAI_API_KEY": "test-key"}):
        result = run_retrieval_and_qa(
            live_config,
            run_id=None,
            source_uri=None,
            question="What happened?",
            all_runs=True,
        )

    assert result["hits"] == 2
    run_ids_in_metadata = [
        hit["metadata"].get("run_id") for hit in result["retrieval_results"]
    ]
    assert "ingest-run-a" in run_ids_in_metadata, (
        "all-runs mode must preserve per-hit run_id='ingest-run-a' in citation metadata"
    )
    assert "ingest-run-b" in run_ids_in_metadata, (
        "all-runs mode must preserve per-hit run_id='ingest-run-b' in citation metadata"
    )
    # The two hits must carry different run_ids — cross-run provenance is distinct
    assert run_ids_in_metadata[0] != run_ids_in_metadata[1], (
        "each hit must carry its own run_id so cross-run provenance is distinguishable"
    )


# ---------------------------------------------------------------------------
# No co-location fallback: chunk mentions must not substitute for participation edges
# ---------------------------------------------------------------------------


def test_chunk_citation_formatter_no_role_fallback_to_collocated_mentions():
    """_chunk_citation_formatter must NOT substitute co-located chunk mentions for missing
    participation-edge roles.

    When a claim has null subject_mention and null object_mention (no HAS_PARTICIPANT edges)
    but the chunk record has a populated `mentions` list (co-located EntityMention nodes),
    the formatter must not infer subject/object roles from those co-located mentions.
    The claim text is still rendered but without any role= annotations.
    """
    from demo.stages.retrieval_and_qa import _chunk_citation_formatter

    # Record with co-located mentions in chunk, but no participation edges on the claim
    record = _make_fake_neo4j_record(
        chunk_id="c-no-fallback",
        run_id="r-no-fallback",
        source_uri="file:///doc.pdf",
        chunk_index=0,
        page=1,
        start_char=0,
        end_char=150,
        chunk_text="Galperin and MercadoLibre appeared in the same document.",
        similarityScore=0.80,
        # Co-located mentions present in the chunk (these must NOT be used for role slots)
        mentions=["Galperin", "MercadoLibre"],
        claims=["Some claim about the company."],
        claim_details=[
            {
                "claim_text": "Some claim about the company.",
                "subject_mention": None,  # no HAS_PARTICIPANT {role: 'subject'} edge
                "object_mention": None,   # no HAS_PARTICIPANT {role: 'object'} edge
            }
        ],
    )
    item = _chunk_citation_formatter(record)

    # Claim context section is rendered (claim text is present)
    assert "[Claim context" in item.content, (
        "Claim context section must still appear when claim_details is present"
    )
    assert "Some claim about the company." in item.content

    # Co-located mentions must NOT appear as subject/object role assignments
    assert "subject='Galperin'" not in item.content, (
        "co-located mention 'Galperin' must not be inferred as subject role"
    )
    assert "object='MercadoLibre'" not in item.content, (
        "co-located mention 'MercadoLibre' must not be inferred as object role"
    )
    assert "subject=" not in item.content, (
        "no subject= annotation must appear when no HAS_PARTICIPANT subject edge exists"
    )
    assert "object=" not in item.content, (
        "no object= annotation must appear when no HAS_PARTICIPANT object edge exists"
    )

    # Co-located mentions list preserved in metadata but not promoted to role slots
    assert item.metadata.get("mentions") == ["Galperin", "MercadoLibre"], (
        "co-located mentions must still be preserved in metadata unchanged"
    )


# ---------------------------------------------------------------------------
# _format_claim_details: edge cases
# ---------------------------------------------------------------------------


def test_format_claim_details_skips_entries_with_empty_claim_text():
    """_format_claim_details must skip claim entries whose claim_text is empty or whitespace.

    A participation edge dataset may include claim rows with blank text due to extraction
    gaps.  These must be silently filtered rather than rendering a blank bullet in context.
    """
    from demo.stages.retrieval_and_qa import _format_claim_details

    details = [
        {
            "claim_text": "",
            "subject_mention": {"name": "Entity A", "match_method": "raw_exact"},
            "object_mention": None,
        },
        {
            "claim_text": "   ",
            "subject_mention": None,
            "object_mention": None,
        },
        {
            "claim_text": "Valid claim text.",
            "subject_mention": {"name": "Entity B", "match_method": "casefold_exact"},
            "object_mention": None,
        },
    ]
    result = _format_claim_details(details)
    # Only the valid entry should produce output
    assert "Valid claim text." in result
    assert "Entity B" in result
    # Entries with empty/whitespace claim_text must be skipped entirely
    assert "Entity A" not in result, (
        "participation edge data for a blank claim_text entry must be silently dropped"
    )
    # The header should appear because there is one valid entry
    assert "[Claim context" in result


def test_format_claim_details_all_empty_claim_text_returns_empty_string():
    """_format_claim_details must return empty string when all entries have empty claim_text."""
    from demo.stages.retrieval_and_qa import _format_claim_details

    details = [
        {"claim_text": "", "subject_mention": None, "object_mention": None},
        {"claim_text": "  ", "subject_mention": None, "object_mention": None},
    ]
    result = _format_claim_details(details)
    assert result == "", (
        "_format_claim_details must return '' when no entry has non-empty claim_text"
    )


# ---------------------------------------------------------------------------
# Dataset-aware latest run selection (fix: ask --dataset must not pick up runs
# from a different dataset in a multi-dataset repo).
# ---------------------------------------------------------------------------


def _live_config(tmp_path: Path, dataset_name: str | None = None) -> Config:
    """Build a minimal live (non-dry-run) Config for testing scope resolution."""
    return Config(
        dry_run=False,
        output_dir=tmp_path,
        neo4j_uri="bolt://example.invalid",
        neo4j_username="neo4j",
        neo4j_password="secret",
        neo4j_database="neo4j",
        openai_model="gpt-4o-mini",
        dataset_name=dataset_name,
    )


def test_fetch_latest_run_id_without_dataset_uses_unfiltered_query(tmp_path: Path):
    """_fetch_latest_unstructured_run_id without dataset_id must NOT filter by dataset_id."""
    from demo.run_demo import _fetch_latest_unstructured_run_id

    captured_queries: list[str] = []
    captured_params: list[dict] = []

    class _FakeRecord:
        def __getitem__(self, idx):
            return "unstructured_ingest-20260101T000000000000Z-aabbccdd"

    class _FakeCheckRecord:
        def __getitem__(self, key):
            if key != "dataset_ids":
                raise KeyError(key)
            return ["demo_dataset_v1"]  # single consistent dataset_id

    class _FakeSession:
        def __init__(self):
            self._call_count = 0

        def run(self, query, **params):
            captured_queries.append(query)
            captured_params.append(params)
            self._call_count += 1
            if self._call_count == 1:
                class _R:
                    def single(self_inner):
                        return _FakeRecord()
                return _R()
            else:
                class _CheckR:
                    def single(self_inner):
                        return _FakeCheckRecord()
                return _CheckR()

        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

    class _FakeDriver:
        def session(self, **kwargs):
            return _FakeSession()

        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

    config = _live_config(tmp_path)
    with mock.patch("neo4j.GraphDatabase.driver", return_value=_FakeDriver()):
        result = _fetch_latest_unstructured_run_id(config, dataset_id=None)

    assert result == "unstructured_ingest-20260101T000000000000Z-aabbccdd"
    assert len(captured_queries) == 2, (
        "Expected 2 queries: one to resolve the run_id and one for the dataset-consistency check"
    )
    assert "dataset_id" not in captured_queries[0], (
        "Query without dataset_id must not include a dataset_id filter clause"
    )
    assert "dataset_id" not in captured_params[0], (
        "Parameters without dataset_id must not pass dataset_id to Neo4j"
    )
    assert "dataset_ids" in captured_queries[1], (
        "Consistency-check query must return a 'dataset_ids' column"
    )
    assert captured_params[1].get("run_id") == "unstructured_ingest-20260101T000000000000Z-aabbccdd", (
        "Consistency-check query must be parameterised with the resolved run_id"
    )


def test_fetch_latest_run_id_with_dataset_filters_by_dataset_id(tmp_path: Path):
    """_fetch_latest_unstructured_run_id with dataset_id must include AND c.dataset_id = $dataset_id."""
    from demo.run_demo import _fetch_latest_unstructured_run_id

    captured_queries: list[str] = []
    captured_params: list[dict] = []

    class _FakeRecord:
        def __getitem__(self, idx):
            return "unstructured_ingest-20260201T000000000000Z-v1run0001"

    class _FakeCheckRecord:
        def __getitem__(self, key):
            if key != "dataset_ids":
                raise KeyError(key)
            return ["demo_dataset_v1"]  # single consistent dataset_id

    class _FakeSession:
        def __init__(self):
            self._call_count = 0

        def run(self, query, **params):
            captured_queries.append(query)
            captured_params.append(params)
            self._call_count += 1
            if self._call_count == 1:
                class _R:
                    def single(self_inner):
                        return _FakeRecord()
                return _R()
            else:
                class _CheckR:
                    def single(self_inner):
                        return _FakeCheckRecord()
                return _CheckR()

        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

    class _FakeDriver:
        def session(self, **kwargs):
            return _FakeSession()

        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

    config = _live_config(tmp_path)
    with mock.patch("neo4j.GraphDatabase.driver", return_value=_FakeDriver()):
        result = _fetch_latest_unstructured_run_id(config, dataset_id="demo_dataset_v1")

    assert result == "unstructured_ingest-20260201T000000000000Z-v1run0001"
    assert len(captured_queries) == 2, (
        "Expected 2 queries: one to resolve the run_id and one for the dataset-consistency check"
    )
    assert "c.dataset_id = $dataset_id" in captured_queries[0], (
        "Query with dataset_id must include the 'AND c.dataset_id = $dataset_id' filter"
    )
    assert captured_params[0].get("dataset_id") == "demo_dataset_v1", (
        "dataset_id parameter must be passed to the Cypher query"
    )
    assert "dataset_ids" in captured_queries[1], (
        "Consistency-check query must return a 'dataset_ids' column"
    )
    assert captured_params[1].get("run_id") == "unstructured_ingest-20260201T000000000000Z-v1run0001", (
        "Consistency-check query must be parameterised with the resolved run_id"
    )


def test_resolve_ask_scope_live_dataset_v1_selects_v1_run(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    """ask --dataset demo_dataset_v1 in live mode must fetch the latest run for v1 only."""
    from demo.run_demo import _resolve_ask_scope, parse_args

    monkeypatch.delenv("UNSTRUCTURED_RUN_ID", raising=False)

    v1_run = "unstructured_ingest-20260301T000000000000Z-v1run0001"

    args = parse_args(["--live", "--dataset", "demo_dataset_v1", "ask"])
    config = _live_config(tmp_path, dataset_name="demo_dataset_v1")

    with mock.patch(
        "demo.run_demo._fetch_latest_unstructured_run_id", return_value=v1_run
    ) as mock_fetch, mock.patch(
        "demo.run_demo.resolve_dataset_root"
    ) as mock_resolve:
        from pathlib import Path as _Path

        mock_resolve.return_value = DatasetRoot(
            root=_Path("/fake/datasets/demo_dataset_v1"),
            dataset_id="demo_dataset_v1",
            pdf_filename="chain_of_custody.pdf",
        )
        run_id, all_runs = _resolve_ask_scope(args, config)

    assert run_id == v1_run
    assert all_runs is False
    mock_fetch.assert_called_once_with(config, dataset_id="demo_dataset_v1")


def test_resolve_ask_scope_live_dataset_v2_selects_v2_run(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    """ask --dataset demo_dataset_v2 in live mode must fetch the latest run for v2 only."""
    from demo.run_demo import _resolve_ask_scope, parse_args

    monkeypatch.delenv("UNSTRUCTURED_RUN_ID", raising=False)

    v2_run = "unstructured_ingest-20260401T000000000000Z-v2run0001"

    args = parse_args(["--live", "--dataset", "demo_dataset_v2", "ask"])
    config = _live_config(tmp_path, dataset_name="demo_dataset_v2")

    with mock.patch(
        "demo.run_demo._fetch_latest_unstructured_run_id", return_value=v2_run
    ) as mock_fetch, mock.patch(
        "demo.run_demo.resolve_dataset_root"
    ) as mock_resolve:
        from pathlib import Path as _Path

        mock_resolve.return_value = DatasetRoot(
            root=_Path("/fake/datasets/demo_dataset_v2"),
            dataset_id="demo_dataset_v2",
            pdf_filename="chain_of_issuance.pdf",
        )
        run_id, all_runs = _resolve_ask_scope(args, config)

    assert run_id == v2_run
    assert all_runs is False
    mock_fetch.assert_called_once_with(config, dataset_id="demo_dataset_v2")


def test_resolve_ask_scope_two_datasets_different_latest_runs(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    """Regression: v1 and v2 each have a distinct latest run; each ask resolves to its own run.

    This is the core multi-dataset regression test from the issue: with both
    demo_dataset_v1 and demo_dataset_v2 ingested, ask --dataset <x> must only
    return the latest run for dataset <x>.
    """
    from demo.run_demo import _resolve_ask_scope, parse_args
    from pathlib import Path as _Path

    monkeypatch.delenv("UNSTRUCTURED_RUN_ID", raising=False)

    # Simulate: v2 was ingested *after* v1 (later timestamp = larger lexicographic order)
    v1_run = "unstructured_ingest-20260301T120000000000Z-v1aabbcc"
    v2_run = "unstructured_ingest-20260401T120000000000Z-v2ddee11"  # newer than v1

    dataset_roots = {
        "demo_dataset_v1": DatasetRoot(
            root=_Path("/fake/datasets/demo_dataset_v1"),
            dataset_id="demo_dataset_v1",
            pdf_filename="chain_of_custody.pdf",
        ),
        "demo_dataset_v2": DatasetRoot(
            root=_Path("/fake/datasets/demo_dataset_v2"),
            dataset_id="demo_dataset_v2",
            pdf_filename="chain_of_issuance.pdf",
        ),
    }

    def _fake_resolve(name):
        return dataset_roots[name]

    def _fake_fetch(config, *, dataset_id=None):
        # Returns the run for the requested dataset; simulates dataset-scoped query
        if dataset_id == "demo_dataset_v1":
            return v1_run
        if dataset_id == "demo_dataset_v2":
            return v2_run
        # Unfiltered (should not happen in this test)
        return v2_run  # latest overall = v2

    # --- Ask for v1 ---
    args_v1 = parse_args(["--live", "--dataset", "demo_dataset_v1", "ask"])
    config_v1 = _live_config(tmp_path, dataset_name="demo_dataset_v1")

    with mock.patch("demo.run_demo._fetch_latest_unstructured_run_id", side_effect=_fake_fetch), \
            mock.patch("demo.run_demo.resolve_dataset_root", side_effect=_fake_resolve):
        run_id_v1, _ = _resolve_ask_scope(args_v1, config_v1)

    assert run_id_v1 == v1_run, (
        f"ask --dataset demo_dataset_v1 must resolve to the v1 run {v1_run!r}, "
        f"not the (newer) v2 run {v2_run!r}; got {run_id_v1!r}"
    )

    # --- Ask for v2 ---
    args_v2 = parse_args(["--live", "--dataset", "demo_dataset_v2", "ask"])
    config_v2 = _live_config(tmp_path, dataset_name="demo_dataset_v2")

    with mock.patch("demo.run_demo._fetch_latest_unstructured_run_id", side_effect=_fake_fetch), \
            mock.patch("demo.run_demo.resolve_dataset_root", side_effect=_fake_resolve):
        run_id_v2, _ = _resolve_ask_scope(args_v2, config_v2)

    assert run_id_v2 == v2_run, (
        f"ask --dataset demo_dataset_v2 must resolve to the v2 run {v2_run!r}; "
        f"got {run_id_v2!r}"
    )


def test_resolve_ask_scope_ambiguous_dataset_falls_back_to_unfiltered(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    """Implicit dataset (no --dataset flag) that raises AmbiguousDatasetError falls back to
    unfiltered latest-run query (legacy single-dataset behaviour preserved)."""
    from demo.run_demo import _resolve_ask_scope, parse_args
    monkeypatch.delenv("UNSTRUCTURED_RUN_ID", raising=False)

    latest_run = "unstructured_ingest-20260401T000000000000Z-fallback0"

    args = parse_args(["--live", "ask"])
    config = _live_config(tmp_path, dataset_name=None)

    with mock.patch(
        "demo.run_demo._fetch_latest_unstructured_run_id", return_value=latest_run
    ) as mock_fetch, mock.patch(
        "demo.run_demo.resolve_dataset_root",
        side_effect=AmbiguousDatasetError("Multiple datasets"),
    ):
        run_id, all_runs = _resolve_ask_scope(args, config)

    assert run_id == latest_run
    assert all_runs is False
    # Falls back: dataset_id=None (no filter) because resolution was ambiguous
    mock_fetch.assert_called_once_with(config, dataset_id=None)


def test_resolve_ask_scope_explicit_dataset_raises_system_exit_on_resolution_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    """Explicit --dataset that fails to resolve must raise SystemExit (fail fast), never silently
    fall back to an unfiltered latest-run query that could pick up the wrong dataset's run."""
    from demo.run_demo import _resolve_ask_scope, parse_args

    monkeypatch.delenv("UNSTRUCTURED_RUN_ID", raising=False)

    args = parse_args(["--live", "--dataset", "nonexistent_dataset", "ask"])
    config = _live_config(tmp_path, dataset_name="nonexistent_dataset")

    with mock.patch(
        "demo.run_demo.resolve_dataset_root",
        side_effect=ValueError("Dataset 'nonexistent_dataset' not found"),
    ), mock.patch(
        "demo.run_demo._fetch_latest_unstructured_run_id"
    ) as mock_fetch:
        with pytest.raises(SystemExit) as exc_info:
            _resolve_ask_scope(args, config)

    assert "nonexistent_dataset" in str(exc_info.value), (
        "SystemExit message must mention the unresolvable dataset name"
    )
    # The fetch must never be called when resolution fails for an explicit dataset
    mock_fetch.assert_not_called()


def test_resolve_ask_scope_fixture_dataset_raises_system_exit_on_resolution_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    """Explicit dataset selection via FIXTURE_DATASET must also fail fast on resolution
    failure, rather than silently falling back to an unfiltered latest-run query.

    This specifically exercises the case where config.dataset_name is None (no --dataset
    CLI flag) but FIXTURE_DATASET env var is set, so resolve_dataset_root() treats it as
    an explicit selection that should fail loudly, not silently fall back."""
    from demo.run_demo import _resolve_ask_scope, parse_args

    monkeypatch.delenv("UNSTRUCTURED_RUN_ID", raising=False)
    monkeypatch.setenv("FIXTURE_DATASET", "nonexistent_env_dataset")

    # No --dataset flag: config.dataset_name is None; only FIXTURE_DATASET drives selection.
    args = parse_args(["--live", "ask"])
    config = _live_config(tmp_path, dataset_name=None)

    with mock.patch(
        "demo.run_demo.resolve_dataset_root",
        side_effect=ValueError("Dataset 'nonexistent_env_dataset' not found"),
    ), mock.patch(
        "demo.run_demo._fetch_latest_unstructured_run_id"
    ) as mock_fetch:
        with pytest.raises(SystemExit) as exc_info:
            _resolve_ask_scope(args, config)

    assert "nonexistent_env_dataset" in str(exc_info.value), (
        "SystemExit message must mention the unresolvable dataset name from FIXTURE_DATASET"
    )
    # The fetch must never be called when resolution fails for an explicit dataset source
    mock_fetch.assert_not_called()


# ---------------------------------------------------------------------------
# Regression tests: UNSTRUCTURED_RUN_ID + --dataset interaction (issue #465)
# ---------------------------------------------------------------------------
# When UNSTRUCTURED_RUN_ID is set and --dataset (or FIXTURE_DATASET) is also
# provided, the env var bypasses dataset-aware run selection and may silently
# retrieve from a run that belongs to a different dataset.  The chosen contract
# is: UNSTRUCTURED_RUN_ID still wins (explicit env var takes precedence) but a
# WARNING is always printed to make the potential mismatch visible to the operator.
# ---------------------------------------------------------------------------


def test_resolve_ask_scope_env_run_id_with_dataset_warns_live(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
):
    """Regression: UNSTRUCTURED_RUN_ID set alongside --dataset in live mode must
    log a WARNING about the potential dataset mismatch and still return the env
    var run_id (explicit env var wins).

    This prevents silent wrong-dataset retrieval from reappearing: if no warning
    is emitted the operator has no indication that the env var may be pointing at
    a different dataset's run."""
    from demo.run_demo import _resolve_ask_scope, parse_args

    v1_env_run = "unstructured_ingest-20260101T000000000000Z-v1run0001"
    monkeypatch.setenv("UNSTRUCTURED_RUN_ID", v1_env_run)
    monkeypatch.delenv("FIXTURE_DATASET", raising=False)

    # --dataset demo_dataset_v2 but env var points at a v1 run — classic mismatch.
    args = parse_args(["--live", "--dataset", "demo_dataset_v2", "ask"])
    config = _live_config(tmp_path, dataset_name="demo_dataset_v2")

    with caplog.at_level(logging.WARNING, logger="demo.run_demo"):
        run_id, all_runs = _resolve_ask_scope(args, config)

    assert run_id == v1_env_run, (
        "UNSTRUCTURED_RUN_ID must take precedence even when --dataset is provided"
    )
    assert all_runs is False

    warning_records = [
        r for r in caplog.records
        if r.levelno == logging.WARNING and "UNSTRUCTURED_RUN_ID" in r.getMessage()
    ]
    assert warning_records, (
        "A WARNING must be logged when UNSTRUCTURED_RUN_ID is used alongside --dataset"
    )
    msg = warning_records[0].getMessage()
    assert v1_env_run in msg, "WARNING must include the UNSTRUCTURED_RUN_ID value"
    assert "--dataset='demo_dataset_v2'" in msg, (
        "WARNING must name --dataset as the source when FIXTURE_DATASET is not set"
    )
    assert "dataset-aware" in msg, (
        "WARNING must mention that UNSTRUCTURED_RUN_ID bypasses dataset-aware selection"
    )


def test_resolve_ask_scope_env_run_id_with_fixture_dataset_warns_live(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
):
    """Regression: UNSTRUCTURED_RUN_ID set alongside FIXTURE_DATASET (no --dataset flag)
    in live mode must also log a WARNING and return the env var run_id.

    FIXTURE_DATASET is an explicit dataset selection just like --dataset; the same
    dataset-integrity risk applies and the same warning must appear."""
    from demo.run_demo import _resolve_ask_scope, parse_args

    v2_env_run = "unstructured_ingest-20260401T000000000000Z-v2run0002"
    monkeypatch.setenv("UNSTRUCTURED_RUN_ID", v2_env_run)
    monkeypatch.setenv("FIXTURE_DATASET", "demo_dataset_v1")

    # No --dataset CLI flag; FIXTURE_DATASET drives dataset selection.
    args = parse_args(["--live", "ask"])
    config = _live_config(tmp_path, dataset_name="demo_dataset_v1")

    with caplog.at_level(logging.WARNING, logger="demo.run_demo"):
        run_id, all_runs = _resolve_ask_scope(args, config)

    assert run_id == v2_env_run
    assert all_runs is False

    warning_records = [
        r for r in caplog.records
        if r.levelno == logging.WARNING and "UNSTRUCTURED_RUN_ID" in r.getMessage()
    ]
    assert warning_records, (
        "A WARNING must be logged when UNSTRUCTURED_RUN_ID is used alongside FIXTURE_DATASET"
    )
    msg = warning_records[0].getMessage()
    assert v2_env_run in msg
    assert "FIXTURE_DATASET='demo_dataset_v1'" in msg, (
        "WARNING must name FIXTURE_DATASET as the source when it is set"
    )


def test_resolve_ask_scope_env_run_id_with_dataset_warns_dry_run(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
):
    """Regression: UNSTRUCTURED_RUN_ID set alongside --dataset in dry-run mode must
    also log a WARNING.

    In dry-run mode Neo4j is not queried, but the dataset-integrity risk is the same:
    the operator may have supplied an env var that belongs to a different dataset."""
    from demo.run_demo import _resolve_ask_scope, parse_args

    v1_env_run = "unstructured_ingest-20260101T000000000000Z-v1run0001"
    monkeypatch.setenv("UNSTRUCTURED_RUN_ID", v1_env_run)
    monkeypatch.delenv("FIXTURE_DATASET", raising=False)

    args = parse_args(["--dry-run", "--dataset", "demo_dataset_v2", "ask"])
    import dataclasses
    config = dataclasses.replace(_dry_run_config(tmp_path), dataset_name="demo_dataset_v2")

    with caplog.at_level(logging.WARNING, logger="demo.run_demo"):
        run_id, all_runs = _resolve_ask_scope(args, config)

    assert run_id == v1_env_run
    assert all_runs is False

    warning_records = [
        r for r in caplog.records
        if r.levelno == logging.WARNING and "UNSTRUCTURED_RUN_ID" in r.getMessage()
    ]
    assert warning_records, (
        "A WARNING must be logged even in dry-run when UNSTRUCTURED_RUN_ID + --dataset are combined"
    )
    msg = warning_records[0].getMessage()
    assert v1_env_run in msg
    assert "--dataset='demo_dataset_v2'" in msg, (
        "WARNING must name --dataset as the source when FIXTURE_DATASET is not set"
    )


def test_resolve_ask_scope_env_run_id_without_dataset_no_warning_live(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
):
    """UNSTRUCTURED_RUN_ID set in live mode WITHOUT --dataset must NOT log a
    dataset-mismatch warning.

    No explicit dataset selection means single-dataset (or all-dataset) posture where
    cross-dataset contamination is not a concern."""
    from demo.run_demo import _resolve_ask_scope, parse_args

    env_run = "unstructured_ingest-20260201T000000000000Z-nodsrun"
    monkeypatch.setenv("UNSTRUCTURED_RUN_ID", env_run)
    monkeypatch.delenv("FIXTURE_DATASET", raising=False)

    args = parse_args(["--live", "ask"])
    config = _live_config(tmp_path, dataset_name=None)

    with caplog.at_level(logging.WARNING, logger="demo.run_demo"):
        run_id, all_runs = _resolve_ask_scope(args, config)

    assert run_id == env_run
    assert all_runs is False

    mismatch_warnings = [
        r for r in caplog.records
        if r.levelno == logging.WARNING and "UNSTRUCTURED_RUN_ID" in r.getMessage()
    ]
    assert not mismatch_warnings, (
        "No dataset-mismatch WARNING should be logged when no explicit dataset is selected"
    )


def test_resolve_ask_scope_env_run_id_dataset_overrides_fixture_dataset_warns_live(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
):
    """Regression: when FIXTURE_DATASET and --dataset are both set but differ, the
    WARNING must attribute the selection to --dataset (the effective override) and
    also mention the overridden FIXTURE_DATASET value.

    This exercises the override branch in _warn_env_run_id_dataset_mismatch and
    ensures the label format does not drift silently when both env var and CLI flag
    are in play simultaneously."""
    from demo.run_demo import _resolve_ask_scope, parse_args

    env_run = "unstructured_ingest-20260301T000000000000Z-override0"
    monkeypatch.setenv("UNSTRUCTURED_RUN_ID", env_run)
    monkeypatch.setenv("FIXTURE_DATASET", "demo_dataset_v1")

    # --dataset explicitly overrides FIXTURE_DATASET with a different value.
    args = parse_args(["--live", "--dataset", "demo_dataset_v2", "ask"])
    config = _live_config(tmp_path, dataset_name="demo_dataset_v2")

    with caplog.at_level(logging.WARNING, logger="demo.run_demo"):
        run_id, all_runs = _resolve_ask_scope(args, config)

    assert run_id == env_run
    assert all_runs is False

    warning_records = [
        r for r in caplog.records
        if r.levelno == logging.WARNING and "UNSTRUCTURED_RUN_ID" in r.getMessage()
    ]
    assert warning_records, (
        "A WARNING must be logged when UNSTRUCTURED_RUN_ID is used alongside --dataset"
    )
    msg = warning_records[0].getMessage()
    assert env_run in msg, "WARNING must include the UNSTRUCTURED_RUN_ID value"
    assert "--dataset='demo_dataset_v2'" in msg, (
        "WARNING must name --dataset as the effective source when it overrides FIXTURE_DATASET"
    )
    assert "FIXTURE_DATASET='demo_dataset_v1'" in msg, (
        "WARNING must include the overridden FIXTURE_DATASET value for operator clarity"
    )


# ---------------------------------------------------------------------------
# Regression tests: explicit --run-id + --dataset mismatch (issue #485)
# ---------------------------------------------------------------------------
# When --run-id and --dataset are both specified in live mode, the CLI must
# check whether the run actually belongs to the selected dataset.  If not, a
# WARNING is printed describing the mismatch so the operator can reconcile their
# arguments.  The explicit --run-id is still used so the operator can investigate
# the mismatch rather than silently failing.
# ---------------------------------------------------------------------------


def test_resolve_ask_scope_explicit_run_id_wrong_dataset_warns_live(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
):
    """Regression: --run-id that belongs to a different dataset than --dataset must
    log a WARNING describing the mismatch in live mode.

    This prevents silent wrong-dataset retrieval: if no warning is emitted, the
    operator has no indication that the run_id comes from a different dataset."""
    from demo.run_demo import _resolve_ask_scope, parse_args

    v1_run = "unstructured_ingest-20260301T000000000000Z-v1run0001"
    monkeypatch.delenv("UNSTRUCTURED_RUN_ID", raising=False)
    monkeypatch.delenv("FIXTURE_DATASET", raising=False)

    # --run-id points at a v1 run but --dataset says v2 — classic mismatch.
    args = parse_args(["--live", "--dataset", "demo_dataset_v2", "ask", "--run-id", v1_run])
    config = _live_config(tmp_path, dataset_name="demo_dataset_v2")

    with mock.patch(
        "demo.run_demo.resolve_dataset_root"
    ) as mock_resolve, mock.patch(
        "demo.run_demo._fetch_dataset_id_for_run", return_value="demo_dataset_v1"
    ) as mock_fetch:
        from pathlib import Path as _Path

        mock_resolve.return_value = DatasetRoot(
            root=_Path("/fake/datasets/demo_dataset_v2"),
            dataset_id="demo_dataset_v2",
            pdf_filename="chain_of_issuance.pdf",
        )
        with caplog.at_level(logging.WARNING, logger="demo.run_demo"):
            run_id, all_runs = _resolve_ask_scope(args, config)

    assert run_id == v1_run, (
        "Explicit --run-id must still be returned even when a dataset mismatch is detected"
    )
    assert all_runs is False

    mock_fetch.assert_called_once_with(config, v1_run)

    warning_records = [
        r for r in caplog.records
        if r.levelno == logging.WARNING and "belongs to dataset" in r.getMessage()
    ]
    assert warning_records, (
        "A WARNING must be logged when --run-id belongs to a different dataset than --dataset"
    )
    msg = warning_records[0].getMessage()
    assert v1_run in msg, "WARNING must include the --run-id value"
    assert "demo_dataset_v1" in msg, "WARNING must include the actual dataset_id of the run"
    assert "demo_dataset_v2" in msg, "WARNING must include the expected dataset_id"
    assert "--dataset='demo_dataset_v2'" in msg, (
        "WARNING must name --dataset as the source when FIXTURE_DATASET is not set"
    )


def test_resolve_ask_scope_explicit_run_id_correct_dataset_no_warning_live(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
):
    """When --run-id belongs to the same dataset as --dataset, no WARNING should be logged."""
    from demo.run_demo import _resolve_ask_scope, parse_args

    v2_run = "unstructured_ingest-20260401T000000000000Z-v2run0001"
    monkeypatch.delenv("UNSTRUCTURED_RUN_ID", raising=False)
    monkeypatch.delenv("FIXTURE_DATASET", raising=False)

    args = parse_args(["--live", "--dataset", "demo_dataset_v2", "ask", "--run-id", v2_run])
    config = _live_config(tmp_path, dataset_name="demo_dataset_v2")

    with mock.patch(
        "demo.run_demo.resolve_dataset_root"
    ) as mock_resolve, mock.patch(
        "demo.run_demo._fetch_dataset_id_for_run", return_value="demo_dataset_v2"
    ):
        from pathlib import Path as _Path

        mock_resolve.return_value = DatasetRoot(
            root=_Path("/fake/datasets/demo_dataset_v2"),
            dataset_id="demo_dataset_v2",
            pdf_filename="chain_of_issuance.pdf",
        )
        with caplog.at_level(logging.WARNING, logger="demo.run_demo"):
            run_id, all_runs = _resolve_ask_scope(args, config)

    assert run_id == v2_run
    assert all_runs is False

    mismatch_warnings = [
        r for r in caplog.records
        if r.levelno == logging.WARNING and "belongs to dataset" in r.getMessage()
    ]
    assert not mismatch_warnings, (
        "No WARNING should be logged when --run-id belongs to the correct dataset"
    )


def test_resolve_ask_scope_explicit_run_id_not_found_no_warning_live(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
):
    """When --run-id is not found in Neo4j (no Chunk nodes), no mismatch WARNING should
    be logged.  The run may simply not exist yet; downstream retrieval will handle it."""
    from demo.run_demo import _resolve_ask_scope, parse_args

    future_run = "unstructured_ingest-20260501T000000000000Z-notfound1"
    monkeypatch.delenv("UNSTRUCTURED_RUN_ID", raising=False)
    monkeypatch.delenv("FIXTURE_DATASET", raising=False)

    args = parse_args(["--live", "--dataset", "demo_dataset_v1", "ask", "--run-id", future_run])
    config = _live_config(tmp_path, dataset_name="demo_dataset_v1")

    with mock.patch(
        "demo.run_demo.resolve_dataset_root"
    ) as mock_resolve, mock.patch(
        # Simulate run not found: returns None
        "demo.run_demo._fetch_dataset_id_for_run", return_value=None
    ):
        from pathlib import Path as _Path

        mock_resolve.return_value = DatasetRoot(
            root=_Path("/fake/datasets/demo_dataset_v1"),
            dataset_id="demo_dataset_v1",
            pdf_filename="chain_of_custody.pdf",
        )
        with caplog.at_level(logging.WARNING, logger="demo.run_demo"):
            run_id, all_runs = _resolve_ask_scope(args, config)

    assert run_id == future_run
    assert all_runs is False

    mismatch_warnings = [
        r for r in caplog.records
        if r.levelno == logging.WARNING and "belongs to dataset" in r.getMessage()
    ]
    assert not mismatch_warnings, (
        "No mismatch WARNING should be logged when the run_id is not found in Neo4j"
    )


def test_resolve_ask_scope_explicit_run_id_no_dataset_no_warning_live(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
):
    """When --run-id is provided but no --dataset or FIXTURE_DATASET is set, no
    dataset-ownership check is performed and no WARNING is logged."""
    from demo.run_demo import _resolve_ask_scope, parse_args

    some_run = "unstructured_ingest-20260301T000000000000Z-nodataset1"
    monkeypatch.delenv("UNSTRUCTURED_RUN_ID", raising=False)
    monkeypatch.delenv("FIXTURE_DATASET", raising=False)

    args = parse_args(["--live", "ask", "--run-id", some_run])
    config = _live_config(tmp_path, dataset_name=None)

    with mock.patch("demo.run_demo._fetch_dataset_id_for_run") as mock_fetch:
        with caplog.at_level(logging.WARNING, logger="demo.run_demo"):
            run_id, all_runs = _resolve_ask_scope(args, config)

    assert run_id == some_run
    assert all_runs is False

    assert mock_fetch.call_count == 0, (
        "_fetch_dataset_id_for_run must not be called when no dataset is selected"
    )

    mismatch_warnings = [
        r for r in caplog.records
        if r.levelno == logging.WARNING and "belongs to dataset" in r.getMessage()
    ]
    assert not mismatch_warnings


def test_resolve_ask_scope_explicit_run_id_wrong_dataset_dry_run_no_check(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
):
    """In dry-run mode, --run-id + --dataset should NOT trigger a Neo4j dataset-ownership
    check (Neo4j is unavailable in dry-run).  No mismatch WARNING should be logged."""
    from demo.run_demo import _resolve_ask_scope, parse_args

    v1_run = "unstructured_ingest-20260301T000000000000Z-v1run0001"
    monkeypatch.delenv("UNSTRUCTURED_RUN_ID", raising=False)
    monkeypatch.delenv("FIXTURE_DATASET", raising=False)

    args = parse_args(["--dry-run", "--dataset", "demo_dataset_v2", "ask", "--run-id", v1_run])
    import dataclasses
    config = dataclasses.replace(_dry_run_config(tmp_path), dataset_name="demo_dataset_v2")

    with mock.patch("demo.run_demo._fetch_dataset_id_for_run") as mock_fetch:
        with caplog.at_level(logging.WARNING, logger="demo.run_demo"):
            run_id, all_runs = _resolve_ask_scope(args, config)

    assert run_id == v1_run
    assert all_runs is False

    assert mock_fetch.call_count == 0, (
        "_fetch_dataset_id_for_run must not be called in dry-run mode"
    )

    # The only WARNING that could appear is from UNSTRUCTURED_RUN_ID; no dataset-ownership
    # check warning should appear because Neo4j isn't available.
    ownership_warnings = [
        r for r in caplog.records
        if r.levelno == logging.WARNING and "belongs to dataset" in r.getMessage()
    ]
    assert not ownership_warnings, (
        "Dataset-ownership WARNING must not appear in dry-run mode"
    )


def test_resolve_ask_scope_explicit_run_id_wrong_fixture_dataset_warns_live(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
):
    """Regression: --run-id + FIXTURE_DATASET (no --dataset flag) with a mismatch
    must also log a WARNING and name FIXTURE_DATASET as the source."""
    from demo.run_demo import _resolve_ask_scope, parse_args

    v2_run = "unstructured_ingest-20260401T000000000000Z-v2run0001"
    monkeypatch.delenv("UNSTRUCTURED_RUN_ID", raising=False)
    monkeypatch.setenv("FIXTURE_DATASET", "demo_dataset_v1")

    # No --dataset CLI flag; FIXTURE_DATASET drives dataset selection.
    args = parse_args(["--live", "ask", "--run-id", v2_run])
    config = _live_config(tmp_path, dataset_name=None)

    with mock.patch(
        "demo.run_demo.resolve_dataset_root"
    ) as mock_resolve, mock.patch(
        "demo.run_demo._fetch_dataset_id_for_run", return_value="demo_dataset_v2"
    ):
        from pathlib import Path as _Path

        mock_resolve.return_value = DatasetRoot(
            root=_Path("/fake/datasets/demo_dataset_v1"),
            dataset_id="demo_dataset_v1",
            pdf_filename="chain_of_custody.pdf",
        )
        with caplog.at_level(logging.WARNING, logger="demo.run_demo"):
            run_id, all_runs = _resolve_ask_scope(args, config)

    assert run_id == v2_run
    assert all_runs is False

    warning_records = [
        r for r in caplog.records
        if r.levelno == logging.WARNING and "belongs to dataset" in r.getMessage()
    ]
    assert warning_records, (
        "A WARNING must be logged when --run-id + FIXTURE_DATASET mismatch"
    )
    msg = warning_records[0].getMessage()
    assert v2_run in msg
    assert "FIXTURE_DATASET='demo_dataset_v1'" in msg, (
        "WARNING must name FIXTURE_DATASET as the source when it is set and --dataset is not"
    )
    assert "demo_dataset_v2" in msg, "WARNING must include the actual dataset_id of the run"


def test_resolve_ask_scope_explicit_run_id_wrong_dataset_overrides_fixture_warns_live(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
):
    """When --dataset overrides FIXTURE_DATASET and --run-id belongs to a third dataset,
    the WARNING must name --dataset as the effective source and also mention FIXTURE_DATASET."""
    from demo.run_demo import _resolve_ask_scope, parse_args

    other_run = "unstructured_ingest-20260501T000000000000Z-other0001"
    monkeypatch.delenv("UNSTRUCTURED_RUN_ID", raising=False)
    monkeypatch.setenv("FIXTURE_DATASET", "demo_dataset_v1")

    # --dataset explicitly overrides FIXTURE_DATASET with a different value.
    args = parse_args(["--live", "--dataset", "demo_dataset_v2", "ask", "--run-id", other_run])
    config = _live_config(tmp_path, dataset_name="demo_dataset_v2")

    with mock.patch(
        "demo.run_demo.resolve_dataset_root"
    ) as mock_resolve, mock.patch(
        "demo.run_demo._fetch_dataset_id_for_run", return_value="demo_dataset_v3"
    ):
        from pathlib import Path as _Path

        mock_resolve.return_value = DatasetRoot(
            root=_Path("/fake/datasets/demo_dataset_v2"),
            dataset_id="demo_dataset_v2",
            pdf_filename="chain_of_issuance.pdf",
        )
        with caplog.at_level(logging.WARNING, logger="demo.run_demo"):
            run_id, all_runs = _resolve_ask_scope(args, config)

    assert run_id == other_run
    assert all_runs is False

    warning_records = [
        r for r in caplog.records
        if r.levelno == logging.WARNING and "belongs to dataset" in r.getMessage()
    ]
    assert warning_records
    msg = warning_records[0].getMessage()
    assert "--dataset='demo_dataset_v2'" in msg, (
        "WARNING must name --dataset as the effective source when it overrides FIXTURE_DATASET"
    )
    assert "FIXTURE_DATASET='demo_dataset_v1'" in msg, (
        "WARNING must include the overridden FIXTURE_DATASET value for operator clarity"
    )


# ---------------------------------------------------------------------------
# Regression test: benchmark failure must not lose the manifest
# ---------------------------------------------------------------------------


def test_benchmark_failure_preserves_manifest_with_error_status(tmp_path: Path):
    """If run_retrieval_benchmark raises, the orchestrator must still write a manifest.

    The manifest's ``retrieval_benchmark`` stage must have ``status: "error"`` and
    capture the exception message and traceback.  All earlier pipeline stages
    (QA/retrieval signals, structured_ingest, etc.) must also be present so that
    partial results are not lost.
    """
    config = _dry_run_config(tmp_path)

    earlier_stages = {
        "structured_stage": {"status": "dry_run"},
        "pdf_stage": {"status": "dry_run"},
        "claim_stage": {"status": "dry_run"},
        "retrieval_stage": {"status": "dry_run"},
        "retrieval_benchmark_stage": {
            "status": "error",
            "error": "simulated benchmark failure",
            "traceback": "Traceback (most recent call last):\n  ...\nRuntimeError: simulated benchmark failure",
        },
    }

    manifest = build_batch_manifest(
        config=config,
        structured_run_id="structured-1",
        unstructured_run_id="unstructured-2",
        **earlier_stages,
    )

    # The benchmark stage must surface the error status.
    benchmark = manifest["stages"]["retrieval_benchmark"]
    assert benchmark["status"] == "error"
    assert "simulated benchmark failure" in benchmark["error"]
    assert "traceback" in benchmark

    # All earlier stages must still be present.
    assert "structured_ingest" in manifest["stages"]
    assert "pdf_ingest" in manifest["stages"]
    assert "claim_and_mention_extraction" in manifest["stages"]
    assert "retrieval_and_qa" in manifest["stages"]

    # QA signals must still be surfaced from the retrieval stage.
    assert "qa_signals" in manifest


def test_benchmark_failure_in_orchestrated_run_writes_manifest(tmp_path: Path):
    """Regression: simulate a benchmark failure during _run_orchestrated and assert
    the manifest file is written with error status and partial pipeline results.
    """
    from unittest.mock import MagicMock, patch

    from demo.run_demo import _run_orchestrated

    config = Config(
        dry_run=True,
        output_dir=tmp_path,
        neo4j_uri="bolt://example.invalid",
        neo4j_username="neo4j",
        neo4j_password="not-used",
        neo4j_database="neo4j",
        openai_model="test-model",
    )

    def _raise_benchmark(*args, **kwargs):
        raise RuntimeError("simulated Neo4j benchmark failure")

    with patch(
        "demo.run_demo.run_retrieval_benchmark",
        side_effect=_raise_benchmark,
    ), patch(
        "demo.run_demo.resolve_dataset_root",
        return_value=MagicMock(
            dataset_id="test_dataset",
            root=tmp_path,
            pdf_filename="test.pdf",
        ),
    ), patch(
        "demo.run_demo._run_pdf_ingest_request_context",
        return_value={"status": "dry_run"},
    ), patch(
        "demo.run_demo._run_claim_extraction_request_context",
        return_value={"status": "dry_run"},
    ), patch(
        "demo.run_demo._run_claim_participation_request_context",
        return_value={"status": "dry_run"},
    ), patch(
        "demo.run_demo._run_entity_resolution_request_context",
        return_value={"status": "dry_run"},
    ), patch(
        "demo.run_demo._run_retrieval_request_context",
        return_value={"status": "dry_run"},
    ), patch(
        "demo.run_demo._run_structured_ingest_request_context",
        return_value={"status": "dry_run"},
    ):
        manifest_path = _run_orchestrated(config)

    assert manifest_path.exists(), "manifest.json must be written even if benchmark fails"

    import json

    manifest = json.loads(manifest_path.read_text())

    benchmark_stage = manifest["stages"].get("retrieval_benchmark")
    assert benchmark_stage is not None, "retrieval_benchmark stage must appear in the manifest"
    assert benchmark_stage["status"] == "error"
    assert "simulated Neo4j benchmark failure" in benchmark_stage["error"]
    assert "traceback" in benchmark_stage

    # Earlier pipeline stages must be present.
    assert "structured_ingest" in manifest["stages"]
    assert "pdf_ingest" in manifest["stages"]
    assert "retrieval_and_qa" in manifest["stages"]


def test_orchestrated_run_warns_when_alignment_version_missing(tmp_path: Path):
    """When the hybrid entity resolution stage does not return alignment_version,
    _run_orchestrated must emit a warning explaining that the benchmark will
    aggregate across all alignment versions instead of scoping to the current cohort.
    """
    import unittest
    from unittest.mock import MagicMock, patch

    from demo.run_demo import _run_orchestrated

    config = Config(
        dry_run=True,
        output_dir=tmp_path,
        neo4j_uri="bolt://example.invalid",
        neo4j_username="neo4j",
        neo4j_password="not-used",
        neo4j_database="neo4j",
        openai_model="test-model",
    )

    # Hybrid stage returns a dict WITHOUT alignment_version — simulates missing key.
    hybrid_stage_without_version = {"status": "dry_run"}

    tc = unittest.TestCase()
    tc.maxDiff = None
    with tc.assertLogs("demo.run_demo", level=logging.WARNING) as captured_logs:
        with patch(
            "demo.run_demo.run_retrieval_benchmark",
            return_value={"status": "dry_run", "artifact_path": str(tmp_path / "bench.json"), "artifact": None},
        ), patch(
            "demo.run_demo.resolve_dataset_root",
            return_value=MagicMock(
                dataset_id="test_dataset",
                root=tmp_path,
                pdf_filename="test.pdf",
            ),
        ), patch(
            "demo.run_demo._run_pdf_ingest_request_context",
            return_value={"status": "dry_run"},
        ), patch(
            "demo.run_demo._run_claim_extraction_request_context",
            return_value={"status": "dry_run"},
        ), patch(
            "demo.run_demo._run_claim_participation_request_context",
            return_value={"status": "dry_run"},
        ), patch(
            "demo.run_demo._run_entity_resolution_request_context",
            return_value=hybrid_stage_without_version,
        ), patch(
            "demo.run_demo._run_retrieval_request_context",
            return_value={"status": "dry_run"},
        ), patch(
            "demo.run_demo._run_structured_ingest_request_context",
            return_value={"status": "dry_run"},
        ):
            _run_orchestrated(config)

    warning_messages = [r for r in captured_logs.output if "WARNING" in r]
    assert any(
        "alignment_version" in msg and "aggregate" in msg.lower()
        for msg in warning_messages
    ), f"Expected alignment_version/aggregate warning in orchestrator log, got: {captured_logs.output}"


def test_orchestrated_run_emits_exactly_one_alignment_version_warning(tmp_path: Path):
    """When alignment_version is missing in an orchestrated run, exactly one warning
    is emitted by the orchestrator logger. This test also verifies that the
    orchestrator passes suppress_alignment_version_warning=True to the benchmark
    stage so a duplicate stage-level warning would be suppressed.
    """
    import unittest
    from unittest.mock import MagicMock, patch

    from demo.run_demo import _run_orchestrated

    config = Config(
        dry_run=True,
        output_dir=tmp_path,
        neo4j_uri="bolt://example.invalid",
        neo4j_username="neo4j",
        neo4j_password="not-used",
        neo4j_database="neo4j",
        openai_model="test-model",
    )

    # Hybrid stage returns a dict WITHOUT alignment_version — simulates missing key.
    hybrid_stage_without_version = {"status": "dry_run"}

    tc = unittest.TestCase()
    tc.maxDiff = None
    mock_run_benchmark = MagicMock(
        return_value={"status": "dry_run", "artifact_path": str(tmp_path / "bench.json"), "artifact": None}
    )
    with tc.assertLogs("demo.run_demo", level=logging.WARNING) as captured_logs:
        with patch(
            "demo.run_demo.run_retrieval_benchmark",
            mock_run_benchmark,
        ), patch(
            "demo.run_demo.resolve_dataset_root",
            return_value=MagicMock(
                dataset_id="test_dataset",
                root=tmp_path,
                pdf_filename="test.pdf",
            ),
        ), patch(
            "demo.run_demo._run_pdf_ingest_request_context",
            return_value={"status": "dry_run"},
        ), patch(
            "demo.run_demo._run_claim_extraction_request_context",
            return_value={"status": "dry_run"},
        ), patch(
            "demo.run_demo._run_claim_participation_request_context",
            return_value={"status": "dry_run"},
        ), patch(
            "demo.run_demo._run_entity_resolution_request_context",
            return_value=hybrid_stage_without_version,
        ), patch(
            "demo.run_demo._run_retrieval_request_context",
            return_value={"status": "dry_run"},
        ), patch(
            "demo.run_demo._run_structured_ingest_request_context",
            return_value={"status": "dry_run"},
        ):
            _run_orchestrated(config)

    # Exactly one alignment_version/aggregate warning on the orchestrator logger.
    all_warning_messages = [r for r in captured_logs.output if "WARNING" in r]
    alignment_warnings = [
        msg for msg in all_warning_messages
        if "alignment_version" in msg and "aggregate" in msg.lower()
    ]
    assert len(alignment_warnings) == 1, (
        f"Expected exactly 1 orchestrator alignment_version/aggregate warning "
        f"(got {len(alignment_warnings)}): {alignment_warnings}"
    )

    # The benchmark must have been called with suppress_alignment_version_warning=True.
    assert mock_run_benchmark.call_count == 1
    _, kwargs = mock_run_benchmark.call_args
    assert kwargs.get("suppress_alignment_version_warning") is True, (
        "Orchestrator must pass suppress_alignment_version_warning=True to run_retrieval_benchmark "
        "when alignment_version is None to avoid a duplicate warning."
    )


def test_e2e_orchestrated_exactly_one_alignment_version_warning(tmp_path: Path):
    """End-to-end regression guard: orchestrated dry-run emits exactly one
    ``alignment_version`` fallback WARNING across *both* the orchestrator logger
    (``demo.run_demo``) and the benchmark-stage logger
    (``demo.stages.retrieval_benchmark``).

    Regression-protection requirement
    ----------------------------------
    This test must fail if deduplication regresses in either direction:

    * **Count > 1**: ``run_retrieval_benchmark`` is emitting a duplicate warning
      even though ``suppress_alignment_version_warning=True`` was passed by
      the orchestrator.
    * **Count == 0**: the orchestrator stopped emitting the warning altogether.

    Unlike ``test_orchestrated_run_emits_exactly_one_alignment_version_warning``,
    this test does **not** mock ``run_retrieval_benchmark``.  The stage runs its
    real dry-run code path (no Neo4j connection required) so that a future
    regression where the stage ignores ``suppress_alignment_version_warning``
    will be caught here.

    For standalone-run coverage (no orchestration, warning must appear) see
    ``TestRunRetrievalBenchmarkDryRun.test_none_alignment_version_emits_warning``
    in ``test_retrieval_benchmark.py``.
    """
    from unittest.mock import MagicMock, patch

    from demo.run_demo import _run_orchestrated

    config = Config(
        dry_run=True,
        output_dir=tmp_path,
        neo4j_uri="bolt://example.invalid",
        neo4j_username="neo4j",
        neo4j_password="not-used",
        neo4j_database="neo4j",
        openai_model="test-model",
    )

    # Hybrid stage returns a dict WITHOUT alignment_version —
    # triggers the orchestrator's alignment_version warning.
    hybrid_stage_without_version: dict[str, object] = {"status": "dry_run"}

    # Capture WARNING-level records from both the orchestrator and the
    # benchmark-stage loggers.  Both loggers are watched simultaneously so
    # a duplicate warning from either side will be detected.
    captured_records: list[logging.LogRecord] = []

    class _CapturingHandler(logging.Handler):
        def emit(self, record: logging.LogRecord) -> None:
            captured_records.append(record)

    handler = _CapturingHandler(level=logging.WARNING)
    loggers_to_watch = [
        logging.getLogger("demo.run_demo"),
        logging.getLogger("demo.stages.retrieval_benchmark"),
    ]
    original_levels = [lg.level for lg in loggers_to_watch]
    for lg in loggers_to_watch:
        lg.addHandler(handler)
        lg.setLevel(logging.WARNING)

    try:
        with patch(
            "demo.run_demo.resolve_dataset_root",
            return_value=MagicMock(
                dataset_id="test_dataset",
                root=tmp_path,
                pdf_filename="test.pdf",
            ),
        ), patch(
            "demo.run_demo._run_pdf_ingest_request_context",
            return_value={"status": "dry_run"},
        ), patch(
            "demo.run_demo._run_claim_extraction_request_context",
            return_value={"status": "dry_run"},
        ), patch(
            "demo.run_demo._run_claim_participation_request_context",
            return_value={"status": "dry_run"},
        ), patch(
            "demo.run_demo._run_entity_resolution_request_context",
            return_value=hybrid_stage_without_version,
        ), patch(
            "demo.run_demo._run_retrieval_request_context",
            return_value={"status": "dry_run"},
        ), patch(
            "demo.run_demo._run_structured_ingest_request_context",
            return_value={"status": "dry_run"},
        ):
            # run_retrieval_benchmark is intentionally NOT mocked.
            # In dry_run mode it writes a stub artifact without connecting to Neo4j.
            _run_orchestrated(config)
    finally:
        for lg, level in zip(loggers_to_watch, original_levels):
            lg.removeHandler(handler)
            lg.setLevel(level)

    alignment_warnings = [
        r for r in captured_records
        if r.levelno >= logging.WARNING
        and "alignment_version" in r.getMessage()
        and "aggregate" in r.getMessage().lower()
    ]

    assert len(alignment_warnings) == 1, (
        f"Expected exactly 1 alignment_version fallback WARNING across "
        f"demo.run_demo and demo.stages.retrieval_benchmark "
        f"(got {len(alignment_warnings)}). "
        f"If count > 1: run_retrieval_benchmark emitted a duplicate warning "
        f"despite suppress_alignment_version_warning=True. "
        f"If count == 0: the orchestrator stopped emitting the warning. "
        f"Records: {[(r.name, r.getMessage()) for r in alignment_warnings]}"
    )

    # The single warning must originate from the orchestrator (demo.run_demo),
    # not from the benchmark stage (demo.stages.retrieval_benchmark).
    assert alignment_warnings[0].name == "demo.run_demo", (
        f"Expected the alignment_version warning to originate from demo.run_demo "
        f"(orchestrator), but got: {alignment_warnings[0].name!r}. "
        f"This means run_retrieval_benchmark emitted the warning instead of "
        f"(or in addition to) the orchestrator."
    )


def test_run_orchestrated_surfaces_stage_warnings(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """A stage result dict with a non-empty 'warnings' list must produce WARNING log records.

    Regression test: _run_orchestrated() must inspect every stage result for a
    top-level 'warnings' list and emit each entry via _logger.warning(), ensuring
    non-fatal stage issues are visible at the orchestration boundary without
    requiring manual artifact inspection.
    """
    from unittest.mock import MagicMock, patch

    from demo.run_demo import _run_orchestrated

    config = Config(
        dry_run=True,
        output_dir=tmp_path,
        neo4j_uri="bolt://example.invalid",
        neo4j_username="neo4j",
        neo4j_password="not-used",
        neo4j_database="neo4j",
        openai_model="test-model",
    )

    # One stage returns a warning; all others return minimal dicts.
    stage_with_warning = {"status": "ok", "warnings": ["synthetic-stage-warning-for-test"]}

    with caplog.at_level(logging.WARNING, logger="demo.run_demo"), patch(
        "demo.run_demo.resolve_dataset_root",
        return_value=MagicMock(
            dataset_id="test_dataset",
            root=tmp_path,
            pdf_filename="test.pdf",
        ),
    ), patch(
        "demo.run_demo._run_pdf_ingest_request_context",
        return_value=stage_with_warning,
    ), patch(
        "demo.run_demo._run_claim_extraction_request_context",
        return_value={"status": "dry_run"},
    ), patch(
        "demo.run_demo._run_claim_participation_request_context",
        return_value={"status": "dry_run"},
    ), patch(
        "demo.run_demo._run_entity_resolution_request_context",
        return_value={"status": "dry_run", "alignment_version": "v1"},
    ), patch(
        "demo.run_demo._run_retrieval_request_context",
        return_value={"status": "dry_run"},
    ), patch(
        "demo.run_demo._run_structured_ingest_request_context",
        return_value={"status": "dry_run"},
    ), patch(
        "demo.run_demo.run_retrieval_benchmark",
        return_value={"status": "dry_run"},
    ):
        _run_orchestrated(config)

    assert any(
        record.levelno == logging.WARNING
        and "synthetic-stage-warning-for-test" in record.getMessage()
        for record in caplog.records
    ), (
        "Expected _run_orchestrated() to emit a WARNING containing the stage warning text, "
        f"but no such record was found. Records: {[r.getMessage() for r in caplog.records]}"
    )


