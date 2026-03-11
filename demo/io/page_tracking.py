"""Page-aware PDF loading and text splitting for the Power Atlas demo pipeline.

``PageTrackingPdfLoader`` wraps the vendor ``PdfLoader`` and records the character
offset of each page boundary into a module-level coordinator so that the downstream
``PageAwareFixedSizeSplitter`` can assign a ``page_number`` (and accurate
``start_char``/``end_char``) to every chunk it creates.

The two classes share state through a module-level ``_coordinator`` instance.
Because the ``SimpleKGPipeline`` processes one document at a time inside a single
asyncio event loop (no concurrent pipeline runs), module-level state is safe here.
"""

from __future__ import annotations

import bisect
import io
import logging
from pathlib import Path
from typing import Any, Dict, Optional, Union

import fsspec
from fsspec import AbstractFileSystem  # type: ignore[import]
from fsspec.implementations.local import LocalFileSystem  # type: ignore[import]
from neo4j_graphrag.experimental.components.pdf_loader import (
    DocumentInfo,
    PdfDocument,
    PdfLoader,
    is_default_fs,
)
from neo4j_graphrag.experimental.components.text_splitters.fixed_size_splitter import (
    FixedSizeSplitter,
)
from neo4j_graphrag.experimental.components.types import TextChunk, TextChunks

# ---------------------------------------------------------------------------
# Local copies of the vendor's word-boundary helpers.
# These mirror _adjust_chunk_start / _adjust_chunk_end from
# neo4j_graphrag.experimental.components.text_splitters.fixed_size_splitter
# and are inlined here so that PageAwareFixedSizeSplitter does not depend on
# private (underscored) vendor symbols that could be removed in a future
# neo4j-graphrag release.
# ---------------------------------------------------------------------------


def _adjust_chunk_start(text: str, approximate_start: int) -> int:
    """Shift the starting index backward if it lands in the middle of a word."""
    start = approximate_start
    if start > 0 and not text[start].isspace() and not text[start - 1].isspace():
        while start > 0 and not text[start - 1].isspace():
            start -= 1
        if start == 0 and not text[0].isspace():
            start = approximate_start
    return start


def _adjust_chunk_end(text: str, start: int, approximate_end: int) -> int:
    """Shift the ending index backward if it lands in the middle of a word."""
    end = approximate_end
    if end < len(text):
        while end > start and not text[end].isspace() and not text[end - 1].isspace():
            end -= 1
        if end == start:
            end = approximate_end
    return end


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

    Uses :func:`bisect.bisect_right` for O(log num_pages) lookup.
    """
    if not page_offsets:
        return 1
    # bisect_right gives the insertion point after all existing entries <= char_offset,
    # i.e. the number of page boundaries that have been crossed.  Clamp to at
    # least 1 to honor the documented contract (result is always >= 1) even if
    # char_offset is negative or precedes the first page boundary.
    return max(1, bisect.bisect_right(page_offsets, char_offset))


def _compute_page_offsets(filepath: str) -> list[int]:
    """Load *filepath* with pypdf and return a list of page-start character offsets.

    The offsets match the concatenated-text representation produced by the
    vendor ``PdfLoader``, which joins pages with ``'\\n'``.  Returns an empty
    list on any error so callers can degrade gracefully.

    .. note::
        This helper is retained as a convenience for callers that only have a
        local file path and do not need the full
        :class:`PageTrackingPdfLoader` pipeline component.  It uses the local
        filesystem ``open()`` and therefore only works for local paths.
    """
    try:
        import pypdf  # type: ignore[import]
    except ImportError:
        _logger.debug(
            "PageTrackingPdfLoader: pypdf not available; page offsets will not be computed. "
            "All chunks will be assigned to page 1."
        )
        return []
    try:
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

    Overrides ``run()`` to extract text and compute page-start character offsets
    in a **single** ``pypdf`` pass, avoiding the double I/O that would result
    from calling ``super().run()`` and then re-parsing the file for offsets.
    The ``PdfDocument`` returned is identical to the vendor implementation.
    """

    async def run(  # type: ignore[override]
        self,
        filepath: Union[str, Path],
        metadata: Optional[Dict[str, str]] = None,
        fs: Optional[Union[AbstractFileSystem, str]] = None,
    ) -> PdfDocument:
        _coordinator.clear()
        if not isinstance(filepath, str):
            filepath = str(filepath)
        # Resolve the filesystem object the same way the vendor does.
        if isinstance(fs, str):
            fs_obj: AbstractFileSystem = fsspec.filesystem(fs)
        elif fs is None:
            fs_obj = LocalFileSystem()
        else:
            fs_obj = fs

        try:
            import pypdf  # type: ignore[import]

            offsets: list[int] = []
            text_parts: list[str] = []
            cumulative = 0
            with fs_obj.open(filepath, "rb") as fp:
                stream = fp if is_default_fs(fs_obj) else io.BytesIO(fp.read())
                reader = pypdf.PdfReader(stream)
                for page in reader.pages:
                    page_text = page.extract_text() or ""
                    offsets.append(cumulative)
                    text_parts.append(page_text)
                    # +1 accounts for the '\n' that joins pages (mirrors vendor logic).
                    cumulative += len(page_text) + 1
            full_text = "\n".join(text_parts)
            _coordinator.set(offsets)
            _logger.debug(
                "PageTrackingPdfLoader: %d page(s) detected for %s",
                len(offsets),
                filepath,
            )
            return PdfDocument(
                text=full_text,
                document_info=DocumentInfo(
                    path=filepath,
                    metadata=self.get_document_metadata(full_text, metadata),
                    document_type="pdf",
                ),
            )
        except ImportError:
            _logger.debug(
                "PageTrackingPdfLoader: pypdf not available; falling back to vendor loader. "
                "All chunks will be assigned to page 1."
            )
        except Exception as exc:
            _logger.warning(
                "PageTrackingPdfLoader: single-pass load failed (%s); "
                "falling back to vendor loader without page tracking.",
                exc,
            )

        # Fallback: delegate to vendor loader; page offsets remain unset.
        return await super().run(filepath, metadata=metadata, fs=fs_obj)


# ---------------------------------------------------------------------------
# PageAwareFixedSizeSplitter
# ---------------------------------------------------------------------------


class PageAwareFixedSizeSplitter(FixedSizeSplitter):
    """FixedSizeSplitter that assigns ``page_number``, ``start_char``, and
    ``end_char`` to every chunk it creates.

    The splitting algorithm is identical to the vendor ``FixedSizeSplitter``,
    but is implemented here so we have direct access to the exact ``start`` and
    ``end`` character positions for each chunk as it is created.  Those character
    offsets are combined with the page offsets stored by
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
                # end_char is inclusive; chunk_size > 0 (enforced by the vendor
                # FixedSizeSplitter.__init__) guarantees end > start for every chunk.
                "end_char": max(end - 1, start),
            }
            chunks.append(TextChunk(text=chunk_text, index=index, metadata=metadata))
            index += 1
            approximate_start = start + step

        return TextChunks(chunks=chunks)


__all__ = [
    "PageAwareFixedSizeSplitter",
    "PageTrackingPdfLoader",
]
