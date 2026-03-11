"""Page-aware PDF loading and text splitting for the Power Atlas demo pipeline.

``PageTrackingPdfLoader`` wraps the vendor ``PdfLoader`` and records the byte-offset
of each page boundary into a module-level coordinator so that the downstream
``PageAwareFixedSizeSplitter`` can assign a ``page_number`` (and accurate
``start_char``/``end_char``) to every chunk it creates.

The two classes share state through a module-level ``_coordinator`` instance.
Because the ``SimpleKGPipeline`` processes one document at a time inside a single
asyncio event loop (no concurrent pipeline runs), module-level state is safe here.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Dict, Optional, Union

from fsspec import AbstractFileSystem  # type: ignore[import]
from neo4j_graphrag.experimental.components.pdf_loader import PdfDocument, PdfLoader
from neo4j_graphrag.experimental.components.text_splitters.fixed_size_splitter import (
    FixedSizeSplitter,
    _adjust_chunk_end,
    _adjust_chunk_start,
)
from neo4j_graphrag.experimental.components.types import TextChunk, TextChunks

_logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Module-level coordinator: shared between PageTrackingPdfLoader and
# PageAwareFixedSizeSplitter within a single pipeline run.
# ---------------------------------------------------------------------------


class _PageOffsetCoordinator:
    """Holds page-start character offsets for the most-recently loaded PDF."""

    def __init__(self) -> None:
        self._offsets: list[int] = []

    def set(self, offsets: list[int]) -> None:
        self._offsets = list(offsets)

    def get(self) -> list[int]:
        return list(self._offsets)

    def clear(self) -> None:
        self._offsets = []


_coordinator = _PageOffsetCoordinator()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _page_number_for_offset(char_offset: int, page_offsets: list[int]) -> int:
    """Return the 1-based page number for a character offset.

    ``page_offsets`` is a list of character offsets at which each page starts
    (index 0 → page 1 starts at offset 0, index 1 → page 2 starts at offset N,
    etc.).  The returned value is always >= 1.
    """
    if not page_offsets:
        return 1
    page_index = 0
    for i, offset in enumerate(page_offsets):
        if offset <= char_offset:
            page_index = i
        else:
            break
    return page_index + 1  # convert to 1-based


def _compute_page_offsets(filepath: str) -> list[int]:
    """Load *filepath* with pypdf and return a list of page-start character offsets.

    The offsets match the concatenated-text representation produced by the
    vendor ``PdfLoader``, which joins pages with ``'\\n'``.  Returns an empty
    list on any error so callers can degrade gracefully.
    """
    try:
        import pypdf  # type: ignore[import]

        offsets: list[int] = []
        cumulative = 0
        with open(filepath, "rb") as fh:
            reader = pypdf.PdfReader(fh)
            for page in reader.pages:
                offsets.append(cumulative)
                page_text = page.extract_text() or ""
                # +1 accounts for the '\n' that PdfLoader inserts between pages
                # via "\n".join(text_parts).  The final page's trailing +1 is
                # harmless: cumulative is not used after the loop exits.
                cumulative += len(page_text) + 1
        return offsets
    except Exception as exc:
        _logger.warning("PageTrackingPdfLoader: could not compute page offsets: %s", exc)
        return []


# ---------------------------------------------------------------------------
# PageTrackingPdfLoader
# ---------------------------------------------------------------------------


class PageTrackingPdfLoader(PdfLoader):
    """PdfLoader that records page-start offsets for use by PageAwareFixedSizeSplitter.

    All PDF loading behaviour is delegated to the vendor ``PdfLoader``.  After
    a successful load this class computes the character offset at which each
    page begins in the concatenated text and stores it in the module-level
    ``_coordinator`` so the downstream splitter can access it.
    """

    async def run(  # type: ignore[override]
        self,
        filepath: Union[str, Path],
        metadata: Optional[Dict[str, str]] = None,
        fs: Optional[Union[AbstractFileSystem, str]] = None,
    ) -> PdfDocument:
        _coordinator.clear()
        result = await super().run(filepath, metadata=metadata, fs=fs)
        offsets = _compute_page_offsets(str(filepath))
        _coordinator.set(offsets)
        _logger.debug(
            "PageTrackingPdfLoader: %d page(s) detected for %s",
            len(offsets),
            filepath,
        )
        return result


# ---------------------------------------------------------------------------
# PageAwareFixedSizeSplitter
# ---------------------------------------------------------------------------


class PageAwareFixedSizeSplitter(FixedSizeSplitter):
    """FixedSizeSplitter that assigns ``page_number``, ``start_char``, and
    ``end_char`` to every chunk it creates.

    The splitting algorithm is identical to the vendor ``FixedSizeSplitter``.
    After splitting, this class locates the actual start position of each chunk
    in the source text and uses the page offsets stored by
    ``PageTrackingPdfLoader`` to assign a 1-based ``page_number``.  Accurate
    ``start_char`` and ``end_char`` values are also written into each chunk's
    ``metadata`` so the post-ingest enrichment query can store them on the
    Neo4j chunk node instead of relying on stride-based estimates.
    """

    async def run(self, text: str) -> TextChunks:  # type: ignore[override]
        page_offsets = _coordinator.get()

        # Replicate the vendor FixedSizeSplitter algorithm so we have access to
        # the exact ``start`` / ``end`` character positions of each chunk.
        chunks: list[TextChunk] = []
        index = 0
        step = self.chunk_size - self.chunk_overlap
        text_length = len(text)
        approximate_start = 0
        skip_adjust_chunk_start = False
        end = 0

        while end < text_length:
            if self.approximate:
                start = (
                    approximate_start
                    if skip_adjust_chunk_start
                    else _adjust_chunk_start(text, approximate_start)
                )
                approximate_end = min(start + self.chunk_size, text_length)
                end = _adjust_chunk_end(text, start, approximate_end)
                skip_adjust_chunk_start = end == approximate_end
            else:
                start = approximate_start
                end = min(start + self.chunk_size, text_length)

            chunk_text = text[start:end]
            page_number = _page_number_for_offset(start, page_offsets)
            metadata: dict[str, Any] = {
                "page_number": page_number,
                "start_char": start,
                # end_char is inclusive; end > start is guaranteed by the loop guard
                # (text_length > 0 and start < text_length), so end >= 1 always.
                "end_char": max(end - 1, start),
            }
            chunks.append(TextChunk(text=chunk_text, index=index, metadata=metadata))
            index += 1
            approximate_start = start + step

        return TextChunks(chunks=chunks)


__all__ = [
    "PageAwareFixedSizeSplitter",
    "PageTrackingPdfLoader",
    "_coordinator",
    "_page_number_for_offset",
    "_compute_page_offsets",
]
