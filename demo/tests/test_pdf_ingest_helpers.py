from __future__ import annotations

import asyncio

import pytest

from demo.stages import pdf_ingest
from demo.io.page_tracking import (
    PageAwareFixedSizeSplitter,
    _coordinator,
    _page_number_for_offset,
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
# PageAwareFixedSizeSplitter
# ---------------------------------------------------------------------------


def _run(coro):
    return asyncio.run(coro)


def test_page_aware_splitter_assigns_page_numbers_from_coordinator():
    """Splitter assigns correct page_number metadata when coordinator has offsets."""
    # Three-page text: each page ~100 chars, page offsets at 0, 100, 200.
    page1 = "A" * 100
    page2 = "B" * 100
    page3 = "C" * 100
    text = page1 + "\n" + page2 + "\n" + page3  # total ~303 chars

    # Page offsets: page 1 starts at 0, page 2 starts at 101 (100 + '\n'), page 3 at 202.
    page_offsets = [0, 101, 202]

    _coordinator.set(page_offsets)
    try:
        splitter = PageAwareFixedSizeSplitter(chunk_size=110, chunk_overlap=0, approximate=False)
        result = _run(splitter.run(text))
    finally:
        _coordinator.clear()

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
    _coordinator.clear()
    splitter = PageAwareFixedSizeSplitter(chunk_size=50, chunk_overlap=0, approximate=False)
    result = _run(splitter.run("x" * 200))

    assert len(result.chunks) > 0
    for chunk in result.chunks:
        assert chunk.metadata is not None
        assert chunk.metadata.get("page_number") == 1


def test_page_aware_splitter_start_char_matches_text_slice():
    """Chunk text must equal text[start_char:end_char+1]."""
    text = "Hello world. This is a longer piece of text for testing. " * 5
    _coordinator.set([0])
    try:
        splitter = PageAwareFixedSizeSplitter(chunk_size=50, chunk_overlap=10, approximate=False)
        result = _run(splitter.run(text))
    finally:
        _coordinator.clear()

    for chunk in result.chunks:
        sc = chunk.metadata["start_char"]
        ec = chunk.metadata["end_char"]
        assert text[sc : ec + 1] == chunk.text


def test_page_aware_splitter_first_chunk_starts_on_page_1():
    """The first chunk must always be on page 1 regardless of total pages."""
    text = "First page content. " * 10 + "\n" + "Second page content. " * 10
    page_offsets = [0, len("First page content. " * 10) + 1]
    _coordinator.set(page_offsets)
    try:
        splitter = PageAwareFixedSizeSplitter(chunk_size=80, chunk_overlap=0, approximate=False)
        result = _run(splitter.run(text))
    finally:
        _coordinator.clear()

    assert result.chunks[0].metadata["page_number"] == 1


def test_page_aware_splitter_index_is_sequential():
    """Chunk indices must start at 0 and be sequential."""
    text = "word " * 200
    _coordinator.set([0])
    try:
        splitter = PageAwareFixedSizeSplitter(chunk_size=100, chunk_overlap=0, approximate=False)
        result = _run(splitter.run(text))
    finally:
        _coordinator.clear()

    for i, chunk in enumerate(result.chunks):
        assert chunk.index == i


def test_page_aware_splitter_empty_text_produces_no_chunks():
    """Splitting empty text must produce no chunks (matches vendor behaviour)."""
    _coordinator.clear()
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
