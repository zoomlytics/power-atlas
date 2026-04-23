from __future__ import annotations

import asyncio
import io
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

import demo.stages.pdf_ingest as pdf_ingest
from demo.io.page_tracking import (
    PageAwareFixedSizeSplitter,
    PageTrackingPdfLoader,
    _clear_page_offsets,
    _get_page_offsets,
    _page_number_for_offset,
    _set_page_offsets,
)


def test_require_positive_int_accepts_positive_int():
    assert pdf_ingest._require_positive_int(5, "param") == 5


@pytest.mark.parametrize("value", [0, -1, 1.5, "a", True])
def test_require_positive_int_rejects_invalid(value):
    with pytest.raises(ValueError) as excinfo:
        pdf_ingest._require_positive_int(value, "param")
    message = str(excinfo.value)
    assert "param" in message
    assert repr(value) in message


# ---------------------------------------------------------------------------
# _page_number_for_offset
# ---------------------------------------------------------------------------


def test_page_number_for_offset_returns_1_when_offsets_empty():
    assert _page_number_for_offset(0, []) == 1
    assert _page_number_for_offset(500, []) == 1


def test_page_number_for_offset_single_page():
    # Single page always maps to page 1.
    offsets = [0]
    assert _page_number_for_offset(0, offsets) == 1
    assert _page_number_for_offset(999, offsets) == 1


def test_page_number_for_offset_two_pages():
    # Page 1 text: chars 0-99, page 2 starts at char 100.
    offsets = [0, 100]
    assert _page_number_for_offset(0, offsets) == 1
    assert _page_number_for_offset(99, offsets) == 1
    assert _page_number_for_offset(100, offsets) == 2
    assert _page_number_for_offset(500, offsets) == 2


def test_page_number_for_offset_three_pages():
    offsets = [0, 200, 400]
    assert _page_number_for_offset(0, offsets) == 1
    assert _page_number_for_offset(199, offsets) == 1
    assert _page_number_for_offset(200, offsets) == 2
    assert _page_number_for_offset(399, offsets) == 2
    assert _page_number_for_offset(400, offsets) == 3
    assert _page_number_for_offset(9999, offsets) == 3


# ---------------------------------------------------------------------------
# PageTrackingPdfLoader
# ---------------------------------------------------------------------------


def _run(coro):
    return asyncio.run(coro)


async def _run_loader_and_capture_offsets(loader, *args, **kwargs):
    result = await loader.run(*args, **kwargs)
    return result, _get_page_offsets()


async def _run_loader_error_and_capture_offsets(loader, *args, **kwargs):
    try:
        await loader.run(*args, **kwargs)
    except Exception as exc:  # noqa: BLE001
        return exc, _get_page_offsets()
    raise AssertionError("Expected loader.run() to raise")


def test_page_tracking_loader_clears_coordinator_at_start():
    """run() clears any stale page offsets at the beginning of each call."""
    _set_page_offsets([0, 100, 200])
    assert _get_page_offsets() == [0, 100, 200], "pre-condition: page offsets store has stale offsets"

    loader = PageTrackingPdfLoader()
    # Force ImportError for 'pypdf' via builtins.__import__ so we reliably
    # exercise the ImportError path (rather than relying on sys.modules=None,
    # which may behave differently depending on import caching state).
    _original_import = __import__

    def _raise_for_pypdf(name, *args, **kwargs):
        if name == "pypdf":
            raise ImportError("pypdf not installed")
        return _original_import(name, *args, **kwargs)

    with patch("builtins.__import__", side_effect=_raise_for_pypdf):
        _, offsets = _run(_run_loader_error_and_capture_offsets(loader, "/nonexistent/path.pdf"))

    # Coordinator must be empty regardless of whether the rest of run() succeeded.
    assert offsets == []


def test_page_tracking_loader_sets_offsets_with_pypdf():
    """run() populates the coordinator with page-start character offsets."""
    page1_text = "Page one content."
    page2_text = "Page two content."

    # Build a mock pypdf reader with two pages.
    mock_page1 = MagicMock()
    mock_page1.extract_text.return_value = page1_text
    mock_page2 = MagicMock()
    mock_page2.extract_text.return_value = page2_text

    mock_reader = MagicMock()
    mock_reader.pages = [mock_page1, mock_page2]

    mock_pypdf = MagicMock()
    mock_pypdf.PdfReader.return_value = mock_reader

    mock_fs = MagicMock()
    mock_fs.open.return_value.__enter__.return_value = io.BytesIO(b"")

    _clear_page_offsets()
    loader = PageTrackingPdfLoader()

    with patch.dict("sys.modules", {"pypdf": mock_pypdf}):
        with patch("demo.io.page_tracking.is_default_fs", return_value=True):
            _, offsets = _run(_run_loader_and_capture_offsets(loader, "/fake/doc.pdf", fs=mock_fs))

    # Page 1 starts at 0; page 2 starts at len(page1_text) + 1 (for the '\n' joiner).
    assert offsets == [0, len(page1_text) + 1]


def test_page_tracking_loader_fallback_leaves_coordinator_empty_on_import_error():
    """When pypdf is not installed, the coordinator is left empty (all chunks → page 1)."""
    _set_page_offsets([0, 100])  # stale offsets from a previous run
    loader = PageTrackingPdfLoader()

    vendor_result = MagicMock()
    _original_import = __import__

    def _raise_for_pypdf(name, *args, **kwargs):
        if name == "pypdf":
            raise ImportError("pypdf not installed")
        return _original_import(name, *args, **kwargs)

    with patch(
        "neo4j_graphrag.experimental.components.data_loader.PdfLoader.run",
        new_callable=AsyncMock,
        return_value=vendor_result,
    ):
        with patch("builtins.__import__", side_effect=_raise_for_pypdf):
            result, offsets = _run(_run_loader_and_capture_offsets(loader, "/fake/doc.pdf"))

    # Coordinator must be empty — no offsets from a failed import.
    assert offsets == []
    assert result is vendor_result


def test_page_tracking_loader_fallback_leaves_coordinator_empty_on_exception():
    """When the single-pass load raises an unexpected error, the coordinator stays empty."""
    _clear_page_offsets()
    loader = PageTrackingPdfLoader()

    mock_pypdf = MagicMock()
    mock_pypdf.PdfReader.side_effect = RuntimeError("corrupt PDF")

    mock_fs = MagicMock()
    mock_fs.open.return_value.__enter__.return_value = io.BytesIO(b"")

    vendor_result = MagicMock()
    with patch(
        "neo4j_graphrag.experimental.components.data_loader.PdfLoader.run",
        new_callable=AsyncMock,
        return_value=vendor_result,
    ):
        with patch.dict("sys.modules", {"pypdf": mock_pypdf}):
            with patch("demo.io.page_tracking.is_default_fs", return_value=True):
                result, offsets = _run(_run_loader_and_capture_offsets(loader, "/fake/doc.pdf", fs=mock_fs))

    assert offsets == []
    assert result is vendor_result


def test_page_tracking_loader_clears_coordinator_on_late_failure():
    """Coordinator is cleared when LoadedDocument construction fails after offsets are computed.

    Guards against the scenario where get_document_metadata() (or any other
    step after offset computation) raises an exception, which must not leave
    stale offsets in the coordinator for the fallback run.
    """
    _clear_page_offsets()
    loader = PageTrackingPdfLoader()

    mock_page = MagicMock()
    mock_page.extract_text.return_value = "Some page content."
    mock_reader = MagicMock()
    mock_reader.pages = [mock_page]

    mock_pypdf = MagicMock()
    mock_pypdf.PdfReader.return_value = mock_reader

    mock_fs = MagicMock()
    mock_fs.open.return_value.__enter__.return_value = io.BytesIO(b"")

    vendor_result = MagicMock()
    with patch(
        "neo4j_graphrag.experimental.components.data_loader.PdfLoader.run",
        new_callable=AsyncMock,
        return_value=vendor_result,
    ):
        with patch.dict("sys.modules", {"pypdf": mock_pypdf}):
            with patch("demo.io.page_tracking.is_default_fs", return_value=True):
                with patch.object(
                    loader,
                    "get_document_metadata",
                    side_effect=RuntimeError("metadata error"),
                ):
                    result, offsets = _run(_run_loader_and_capture_offsets(loader, "/fake/doc.pdf", fs=mock_fs))

    # Offsets must NOT have been leaked into the coordinator.
    assert offsets == []
    assert result is vendor_result


# ---------------------------------------------------------------------------
# PageAwareFixedSizeSplitter
# ---------------------------------------------------------------------------


def test_page_aware_splitter_assigns_page_numbers_from_coordinator():
    """Splitter assigns correct page_number metadata when coordinator has offsets."""
    # Three-page text: each page ~100 chars, page offsets at 0, 100, 200.
    page1 = "A" * 100
    page2 = "B" * 100
    page3 = "C" * 100
    text = page1 + "\n" + page2 + "\n" + page3  # total ~303 chars

    # Page offsets: page 1 starts at 0, page 2 starts at 101 (100 + '\n'), page 3 at 202.
    page_offsets = [0, 101, 202]

    _set_page_offsets(page_offsets)
    try:
        splitter = PageAwareFixedSizeSplitter(chunk_size=110, chunk_overlap=0, approximate=False)
        result = _run(splitter.run(text))
    finally:
        _clear_page_offsets()

    assert len(result.chunks) > 0
    assert page_offsets, "page_offsets must be non-empty for this test to exercise page mapping"
    for chunk in result.chunks:
        assert chunk.metadata is not None
        assert "start_char" in chunk.metadata
        assert "end_char" in chunk.metadata
        sc = chunk.metadata["start_char"]
        ec = chunk.metadata["end_char"]
        assert ec >= sc
        # Page number must match what _page_number_for_offset would give for
        # this chunk's start offset.
        expected_page = _page_number_for_offset(sc, page_offsets)
        assert chunk.metadata["page_number"] == expected_page


def test_page_aware_splitter_assigns_page_1_without_coordinator_offsets():
    """Splitter defaults to page 1 for all chunks when no page offsets are available."""
    _clear_page_offsets()
    splitter = PageAwareFixedSizeSplitter(chunk_size=50, chunk_overlap=0, approximate=False)
    result = _run(splitter.run("x" * 200))

    assert len(result.chunks) > 0
    for chunk in result.chunks:
        assert chunk.metadata is not None
        assert chunk.metadata.get("page_number") == 1


def test_page_aware_splitter_start_char_matches_text_slice():
    """Chunk text must equal text[start_char:end_char+1]."""
    text = "Hello world. This is a longer piece of text for testing. " * 5
    _set_page_offsets([0])
    try:
        splitter = PageAwareFixedSizeSplitter(chunk_size=50, chunk_overlap=10, approximate=False)
        result = _run(splitter.run(text))
    finally:
        _clear_page_offsets()

    for chunk in result.chunks:
        sc = chunk.metadata["start_char"]
        ec = chunk.metadata["end_char"]
        assert text[sc : ec + 1] == chunk.text


def test_page_aware_splitter_first_chunk_starts_on_page_1():
    """The first chunk must always be on page 1 regardless of total pages."""
    text = "First page content. " * 10 + "\n" + "Second page content. " * 10
    page_offsets = [0, len("First page content. " * 10) + 1]
    _set_page_offsets(page_offsets)
    try:
        splitter = PageAwareFixedSizeSplitter(chunk_size=80, chunk_overlap=0, approximate=False)
        result = _run(splitter.run(text))
    finally:
        _clear_page_offsets()

    assert result.chunks[0].metadata["page_number"] == 1


def test_page_aware_splitter_index_is_sequential():
    """Chunk indices must start at 0 and be sequential."""
    text = "word " * 200
    _set_page_offsets([0])
    try:
        splitter = PageAwareFixedSizeSplitter(chunk_size=100, chunk_overlap=0, approximate=False)
        result = _run(splitter.run(text))
    finally:
        _clear_page_offsets()

    for i, chunk in enumerate(result.chunks):
        assert chunk.index == i


def test_page_aware_splitter_empty_text_produces_no_chunks():
    """Splitting empty text must produce no chunks (matches vendor behaviour)."""
    _clear_page_offsets()
    splitter = PageAwareFixedSizeSplitter(chunk_size=100, chunk_overlap=0, approximate=False)
    result = _run(splitter.run(""))
    assert result.chunks == []


# ---------------------------------------------------------------------------
# PageAwareFixedSizeSplitter — construction-time validation
# (The vendor FixedSizeSplitter.__init__ already guards against step<=0;
# these tests verify that protection is in place so the while-loop
# can never become infinite.)
# ---------------------------------------------------------------------------


def test_page_aware_splitter_raises_at_construction_for_zero_chunk_size():
    """chunk_size=0 must raise ValueError at construction (vendor validates)."""
    with pytest.raises(ValueError, match="chunk_size"):
        PageAwareFixedSizeSplitter(chunk_size=0, chunk_overlap=0, approximate=False)


def test_page_aware_splitter_raises_at_construction_for_negative_chunk_size():
    """chunk_size<0 must raise ValueError at construction (vendor validates)."""
    with pytest.raises(ValueError, match="chunk_size"):
        PageAwareFixedSizeSplitter(chunk_size=-10, chunk_overlap=0, approximate=False)


def test_page_aware_splitter_raises_at_construction_when_overlap_equals_chunk_size():
    """chunk_overlap == chunk_size (step=0) must raise ValueError at construction."""
    with pytest.raises(ValueError, match="chunk_overlap"):
        PageAwareFixedSizeSplitter(chunk_size=50, chunk_overlap=50, approximate=False)


def test_page_aware_splitter_raises_at_construction_when_overlap_exceeds_chunk_size():
    """chunk_overlap > chunk_size (negative step) must raise ValueError at construction."""
    with pytest.raises(ValueError, match="chunk_overlap"):
        PageAwareFixedSizeSplitter(chunk_size=50, chunk_overlap=60, approximate=False)


# ---------------------------------------------------------------------------
# _run_pipeline_with_cleanup
# ---------------------------------------------------------------------------


class _FakeLLMWithAsyncClient:
    """LLM stub that owns an async_client with a close() coroutine."""

    def __init__(self):
        self.async_client = MagicMock()
        self.async_client.close = AsyncMock()


class _FakeLLMWithoutAsyncClient:
    """LLM stub that has no async_client attribute at all."""


class _FakePipelineConfig:
    """Minimal pipeline config stub that exposes _global_data."""

    def __init__(self, llms):
        self._global_data = {"llm_config": llms}


class _FakePipelineRunner:
    """Minimal PipelineRunner stub."""

    def __init__(self, config, result="ok"):
        self.config = config
        self._result = result

    async def run(self, run_params):
        return self._result


def test_run_pipeline_with_cleanup_closes_llm_async_client():
    """async_client.close() is awaited for every LLM that owns one."""
    llm = _FakeLLMWithAsyncClient()
    config = _FakePipelineConfig({"default": llm})
    runner = _FakePipelineRunner(config, result="pipeline_result")

    result = _run(pdf_ingest._run_pipeline_with_cleanup(runner, {}))

    assert result == "pipeline_result"
    llm.async_client.close.assert_awaited_once()


def test_run_pipeline_with_cleanup_skips_llm_without_async_client():
    """LLMs without an async_client attribute are silently skipped."""
    llm = _FakeLLMWithoutAsyncClient()
    config = _FakePipelineConfig({"default": llm})
    runner = _FakePipelineRunner(config, result="ok")

    # Must not raise.
    _run(pdf_ingest._run_pipeline_with_cleanup(runner, {}))


def test_run_pipeline_with_cleanup_handles_multiple_llms():
    """All LLMs in llm_config have their async_client closed."""
    llm_a = _FakeLLMWithAsyncClient()
    llm_b = _FakeLLMWithAsyncClient()
    config = _FakePipelineConfig({"a": llm_a, "b": llm_b})
    runner = _FakePipelineRunner(config)

    _run(pdf_ingest._run_pipeline_with_cleanup(runner, {}))

    llm_a.async_client.close.assert_awaited_once()
    llm_b.async_client.close.assert_awaited_once()


def test_run_pipeline_with_cleanup_closes_llms_even_on_pipeline_error():
    """async_client.close() is called in the finally block even if pipeline.run() raises."""

    class _ErrorRunner:
        def __init__(self, config):
            self.config = config

        async def run(self, run_params):
            raise RuntimeError("pipeline boom")

    llm = _FakeLLMWithAsyncClient()
    config = _FakePipelineConfig({"default": llm})
    runner = _ErrorRunner(config)

    with pytest.raises(RuntimeError, match="pipeline boom"):
        _run(pdf_ingest._run_pipeline_with_cleanup(runner, {}))

    llm.async_client.close.assert_awaited_once()


def test_run_pipeline_with_cleanup_tolerates_close_error():
    """An error from async_client.close() is logged as a warning and the pipeline result is still returned."""
    llm = _FakeLLMWithAsyncClient()
    llm.async_client.close = AsyncMock(side_effect=RuntimeError("close failed"))
    config = _FakePipelineConfig({"default": llm})
    runner = _FakePipelineRunner(config, result="done")

    with patch("demo.stages.pdf_ingest._logger") as mock_logger:
        # Should not raise even though close() raises.
        result = _run(pdf_ingest._run_pipeline_with_cleanup(runner, {}))

    assert result == "done"
    mock_logger.warning.assert_called_once()
    warning_msg = mock_logger.warning.call_args[0][0]
    assert "async_client" in warning_msg


def test_run_pipeline_with_cleanup_handles_none_config():
    """When pipeline.config is None the function runs without error."""

    class _NoneConfigRunner:
        config = None

        async def run(self, run_params):
            return "no_config"

    result = _run(pdf_ingest._run_pipeline_with_cleanup(_NoneConfigRunner(), {}))
    assert result == "no_config"
