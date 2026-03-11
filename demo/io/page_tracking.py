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
]
