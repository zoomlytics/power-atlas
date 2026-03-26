"""Doc-vs-interface contract drift checks for the retrieval/citation result contract.

Reads the §4 scenario JSON examples directly from
``docs/architecture/retrieval-citation-result-contract-v0.1.md`` and runs the
corresponding scenarios through ``run_retrieval_and_qa()`` to detect drift between
the documented contract and the live implementation.

Each documented scenario is driven using fixture values that mirror those in
``test_retrieval_result_contract.py``.

A test failure here means **either**:

- The documentation was updated but the implementation was not, **or**
- The implementation changed a field or its value and the documentation is now stale.

Maintainers must explicitly reconcile the difference before merging.

Coverage
--------
``TestDocContractDrift``
    Parametrized end-to-end drift checks.

    - ``test_doc_has_all_fixture_sections`` — every section ID in
      ``_SECTION_FIXTURES`` must be present as a ``### 4.x`` heading in the doc.
    - ``test_all_doc_sections_are_mapped_or_excluded`` — every ``### 4.x`` heading
      in the doc is either in ``_SECTION_FIXTURES`` or explicitly noted in
      ``_EXCLUDED_SECTIONS`` so nothing falls through silently.
    - ``test_no_drift_between_doc_and_runtime[4.x]`` — for each mapped section,
      concrete (non-placeholder) field values from the doc JSON must match the
      live runtime output.
"""
from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from demo.stages.retrieval_and_qa import run_retrieval_and_qa

# ---------------------------------------------------------------------------
# Contract document location
# ---------------------------------------------------------------------------

_CONTRACT_DOC_PATH: Path = (
    Path(__file__).parents[2]
    / "docs"
    / "architecture"
    / "retrieval-citation-result-contract-v0.1.md"
)

# ---------------------------------------------------------------------------
# Shared test fixtures (reused from test_retrieval_result_contract.py)
# ---------------------------------------------------------------------------

from demo.tests.test_retrieval_result_contract import (
    _CITED_ANSWER,
    _EMPTY_CHUNK_METADATA,
    _LIVE_CONFIG,
    _LIVE_ITEM_METADATA,
    _UNCITED_ANSWER,
)
#: Metadata for a hit that has a fully-populated ``citation_object`` but no
#: ``citation_token``.  In all-runs mode this triggers repair (preconditions met)
#: but repair cannot apply because there is no token to append (§4.7).  The
#: ``citation_object`` is present so no "missing optional citation fields"
#: operational warning is emitted — matching the single-warning expectation in
#: the doc's §4.7 JSON example.
_HIT_METADATA_NO_TOKEN: dict[str, object] = {
    "chunk_id": "c-no-token",
    "citation_object": {
        "chunk_id": "c-no-token",
        "run_id": "r1",
        "source_uri": "file:///doc.pdf",
        "chunk_index": 0,
        "page": 1,
        "start_char": 0,
        "end_char": 50,
    },
}

# ---------------------------------------------------------------------------
# Doc parsing
# ---------------------------------------------------------------------------


def _parse_section_json_from_doc() -> dict[str, dict[str, Any]]:
    """Parse JSON examples from §4.x subsections of the contract document.

    Returns
    -------
    dict[str, dict]
        Mapping of section number (e.g. ``"4.1"``) to the parsed JSON dict.
        Sections that contain no JSON code block are omitted.

    Raises
    ------
    FileNotFoundError
        If the contract document does not exist at ``_CONTRACT_DOC_PATH``.
    ValueError
        If a JSON code block in a §4.x section cannot be parsed.
    """
    text = _CONTRACT_DOC_PATH.read_text(encoding="utf-8")

    # Each ### 4.x heading starts a subsection; body runs until the next heading.
    section_re = re.compile(
        r"^### (4\.\d+)[^\n]*\n(.*?)(?=^### |^## |\Z)",
        re.MULTILINE | re.DOTALL,
    )
    json_block_re = re.compile(r"```json\r?\n(.*?)\r?\n```", re.DOTALL)

    sections: dict[str, dict[str, Any]] = {}
    for m in section_re.finditer(text):
        section_id = m.group(1)
        body = m.group(2)
        jm = json_block_re.search(body)
        if not jm:
            continue
        raw = jm.group(1)
        try:
            sections[section_id] = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise ValueError(
                f"Failed to parse JSON block in §{section_id} of {_CONTRACT_DOC_PATH}: "
                f"{exc}\n--- raw block ---\n{raw}"
            ) from exc
    return sections


def _find_doc_section_ids() -> set[str]:
    """Return all ``### 4.x`` section IDs found in the contract document."""
    text = _CONTRACT_DOC_PATH.read_text(encoding="utf-8")
    return set(re.findall(r"^### (4\.\d+)", text, re.MULTILINE))


# ---------------------------------------------------------------------------
# Comparison helpers
# ---------------------------------------------------------------------------

#: Top-level and nested string fields that carry example answer text.  These
#: may contain placeholder citation tokens with ``…`` so only the Python type
#: (``str``) is verified rather than the exact value.
_ANSWER_TEXT_FIELDS: frozenset[str] = frozenset({"answer", "raw_answer"})

#: Fields where null-vs-non-null is the contractual assertion.  The specific
#: non-null value (e.g. a chunk ID like ``"xyz"``) is illustrative only.
_NULL_VS_NONNULL_FIELDS: frozenset[str] = frozenset({"citation_repair_source_chunk_id"})


def _collect_drifts(
    section_id: str,
    doc: dict[str, Any],
    runtime: dict[str, Any],
    *,
    path: str = "",
) -> list[str]:
    """Recursively compare *doc* with *runtime*, returning drift messages.

    Comparison rules applied in precedence order:

    1. **Missing fields** — a field present in *doc* but absent from *runtime*
       is always reported as drift.
    2. **Nested dict** — recurse into both dicts.
    3. **List** — compare **length** first, then (when lengths match) compare
       items element-by-element using the same rules as for their types.
       List items may carry placeholder chunk IDs or illustrative answer text;
       such placeholder-style differences are normalized/ignored, but real
       content or structural drift (including a length mismatch) is still
       caught.
    4. **``None``** — exact match required.
    5. **``bool``** — exact match required (``is`` check, not ``==``, to
       distinguish ``True``/``False`` from ``1``/``0``).
    6. **``int``** — exact match required.
    7. **``str``**:

       * Fields in ``_ANSWER_TEXT_FIELDS``: Python type check only.
       * Fields in ``_NULL_VS_NONNULL_FIELDS`` when doc value is non-null:
         runtime must also be non-null.
       * Strings containing ``…``: illustrative placeholder; skipped.
       * All other strings (``evidence_level``, ``citation_repair_strategy``,
         warning messages without placeholder IDs, …): exact match required.

    Parameters
    ----------
    section_id:
        The ``§4.x`` identifier used in drift messages.
    doc:
        The dict parsed from the doc's JSON block.
    runtime:
        The live result dict from ``run_retrieval_and_qa()``.
    path:
        Dot-joined path prefix for nested field names (used in messages).
    """
    drifts: list[str] = []

    for field, doc_val in doc.items():
        field_path = f"{path}.{field}" if path else field

        if field not in runtime:
            drifts.append(
                f"[§{section_id}] {field_path!r} is in the doc but absent "
                f"from the runtime result"
            )
            continue

        rt_val = runtime[field]

        # --- Nested dict ---
        if isinstance(doc_val, dict):
            if not isinstance(rt_val, dict):
                drifts.append(
                    f"[§{section_id}] {field_path!r}: doc has dict,"
                    f" runtime has {type(rt_val).__name__!r}"
                )
            else:
                drifts.extend(
                    _collect_drifts(section_id, doc_val, rt_val, path=field_path)
                )
            continue

        # --- List: compare length, and optionally elements when concrete ---
        if isinstance(doc_val, list):
            if not isinstance(rt_val, list):
                drifts.append(
                    f"[§{section_id}] {field_path!r}: doc has list,"
                    f" runtime has {type(rt_val).__name__!r}"
                )
            else:
                # Helper: detect whether the doc list uses explicit placeholders,
                # in which case we only enforce list length, not per-element equality.
                def _list_uses_placeholders(list_val: list[Any]) -> bool:
                    for elem in list_val:
                        if isinstance(elem, str) and re.search(r"\{[^}]+\}", elem):
                            return True
                    return False

                # Helper: normalize variable parts (e.g. chunk IDs) in list elements
                # so wording drift is still detected while ignoring dynamic IDs.
                def _normalize_list_element(val: Any) -> Any:
                    if not isinstance(val, str):
                        return val
                    # Normalize chunk identifiers in warning strings such as
                    # "Chunk 'abc123' ..." -> "Chunk '<id>' ..."
                    normalized = re.sub(
                        r"Chunk '([^']+)'",
                        "Chunk '<id>'",
                        val,
                    )
                    return normalized

                if len(doc_val) != len(rt_val):
                    drifts.append(
                        f"[§{section_id}] {field_path!r}: doc lists {len(doc_val)} item(s),"
                        f" runtime has {len(rt_val)} item(s) — runtime value: {rt_val!r}"
                    )
                # When the doc does not use placeholders, compare normalized elements
                # to detect wording drift in concrete list values (e.g. warnings).
                if not _list_uses_placeholders(doc_val):
                    for idx, (doc_item, rt_item) in enumerate(zip(doc_val, rt_val)):
                        norm_doc = _normalize_list_element(doc_item)
                        norm_rt = _normalize_list_element(rt_item)
                        if norm_doc != norm_rt:
                            drifts.append(
                                f"[§{section_id}] {field_path!r}[{idx}]:"
                                f" doc={doc_item!r}, runtime={rt_item!r}"
                            )
            continue

        # --- None ---
        if doc_val is None:
            if rt_val is not None:
                drifts.append(
                    f"[§{section_id}] {field_path!r}: doc=null,"
                    f" runtime={rt_val!r}"
                )
            continue

        # --- bool (must precede int because bool is a subclass of int) ---
        if isinstance(doc_val, bool):
            if doc_val is not rt_val:
                drifts.append(
                    f"[§{section_id}] {field_path!r}:"
                    f" doc={doc_val!r}, runtime={rt_val!r}"
                )
            continue

        # --- int ---
        if isinstance(doc_val, int):
            if doc_val != rt_val:
                drifts.append(
                    f"[§{section_id}] {field_path!r}:"
                    f" doc={doc_val!r}, runtime={rt_val!r}"
                )
            continue

        # --- str ---
        if isinstance(doc_val, str):
            # Resolve the leaf field name for set membership checks.
            leaf = field_path.rsplit(".", 1)[-1] if "." in field_path else field_path

            if leaf in _ANSWER_TEXT_FIELDS:
                # Answer text in the contract doc is largely illustrative. For these
                # fields we only require the runtime value to be a string, to avoid
                # spurious drift failures when the documented prose changes.
                if not isinstance(rt_val, str):
                    drifts.append(
                        f"[§{section_id}] {field_path!r}:"
                        f" doc has str, runtime has {type(rt_val).__name__!r}"
                    )
                continue

            if leaf in _NULL_VS_NONNULL_FIELDS:
                # Non-null in doc → runtime must also be non-null.
                if rt_val is None:
                    drifts.append(
                        f"[§{section_id}] {field_path!r}:"
                        f" doc is non-null ({doc_val!r}), runtime is null"
                    )
                continue

            if "…" in doc_val:
                # Contains the Unicode ellipsis used in placeholder citation
                # tokens; skip without comparing.
                continue

            # All other strings are contractual — require exact match.
            if doc_val != rt_val:
                drifts.append(
                    f"[§{section_id}] {field_path!r}:"
                    f" doc={doc_val!r}, runtime={rt_val!r}"
                )
            continue

        # --- fallback for previously-unhandled scalar types (e.g. float) ---
        if isinstance(doc_val, float):
            # For floats we require exact numeric equality. If the contract
            # ever needs tolerance-based comparison, this is the place to
            # update.
            if doc_val != rt_val:
                drifts.append(
                    f"[§{section_id}] {field_path!r}:"
                    f" doc={doc_val!r}, runtime={rt_val!r}"
                )
            continue

        # Any other unexpected type should cause the test to fail loudly so
        # that the contract and comparator can be updated together.
        raise TypeError(
            f"[§{section_id}] {field_path!r}: unsupported doc value type"
            f" {type(doc_val).__name__!r} (value={doc_val!r}) in contract"
        )
    return drifts


# ---------------------------------------------------------------------------
# Runtime execution helpers
# ---------------------------------------------------------------------------


def _make_rag_result(answer: str, items_metadata: list[dict[str, object]]) -> MagicMock:
    """Build a mock RAG search result carrying *answer* and *items_metadata*."""
    mock_items = [
        MagicMock(content=f"chunk_content_{i}", metadata=meta)
        for i, meta in enumerate(items_metadata)
    ]
    mock_result = MagicMock()
    mock_result.answer = answer
    mock_result.retriever_result.items = mock_items
    return mock_result


def _run_with_mocked_retrieval(
    answer: str,
    items_metadata: list[dict[str, object]],
    *,
    all_runs: bool = True,
    run_id: str | None = None,
) -> dict[str, object]:
    """Drive ``run_retrieval_and_qa`` with mocked Neo4j / RAG infrastructure.

    Parameters
    ----------
    answer:
        Answer text the mocked RAG layer will return.
    items_metadata:
        Per-item metadata dicts for the mock retrieval result.
    all_runs:
        Whether to use the all-runs code path.
    run_id:
        Required when *all_runs* is ``False``.
    """
    if not all_runs and run_id is None:
        raise ValueError("run_id is required when all_runs is False")
    mock_rag = MagicMock()
    mock_rag.search.return_value = _make_rag_result(answer, items_metadata)
    with (
        patch.dict(os.environ, {"OPENAI_API_KEY": "fake-key"}),
        patch("neo4j.GraphDatabase.driver"),
        patch("demo.stages.retrieval_and_qa._build_retriever_and_rag") as mock_build,
    ):
        mock_build.return_value = (MagicMock(), mock_rag)
        return run_retrieval_and_qa(
            _LIVE_CONFIG,
            all_runs=all_runs,
            run_id=run_id,
            question="What is the claim?",
        )


# ---------------------------------------------------------------------------
# Section-to-fixture mapping
# ---------------------------------------------------------------------------

#: Maps each §4.x section ID to the kwargs passed to ``_run_with_mocked_retrieval``.
#: Only sections whose expected behaviour is fully deterministic without internal
#: mock patching are listed here.
_SECTION_FIXTURES: dict[str, dict[str, Any]] = {
    "4.1": {
        "answer": _CITED_ANSWER,
        "items_metadata": [_LIVE_ITEM_METADATA],
        "all_runs": True,
    },
    "4.2": {
        "answer": _UNCITED_ANSWER,
        "items_metadata": [_LIVE_ITEM_METADATA],
        "all_runs": False,
        "run_id": "r1",
    },
    "4.3": {
        "answer": _UNCITED_ANSWER,
        "items_metadata": [_LIVE_ITEM_METADATA],
        "all_runs": True,
    },
    "4.5": {
        "answer": "",
        "items_metadata": [],
        "all_runs": True,
    },
    "4.6": {
        "answer": _CITED_ANSWER,
        "items_metadata": [_EMPTY_CHUNK_METADATA],
        "all_runs": True,
    },
    "4.7": {
        "answer": _UNCITED_ANSWER,
        "items_metadata": [_HIT_METADATA_NO_TOKEN],
        "all_runs": True,
    },
}

#: §4.x sections that require internal mock patching and are intentionally
#: excluded from automated doc-vs-runtime comparison.  Every section in the doc
#: that is NOT in ``_SECTION_FIXTURES`` must have an entry here so that newly
#: added doc sections are not silently overlooked.
_EXCLUDED_SECTIONS: dict[str, str] = {
    "4.4": (
        "Requires patching _apply_citation_repair to produce a partial repair; "
        "covered by TestRunRetrievalAndQaDocumentedScenarios. "
        "test_s4_4_repair_applied_answer_still_degraded in "
        "test_retrieval_result_contract.py."
    ),
}


# ---------------------------------------------------------------------------
# Test class
# ---------------------------------------------------------------------------


class TestDocContractDrift:
    """Detect drift between §4 JSON examples in the contract doc and live runtime output.

    For each §4.x section mapped in ``_SECTION_FIXTURES`` this class:

    1. Reads the JSON example directly from the contract markdown document.
    2. Runs ``run_retrieval_and_qa()`` with the corresponding fixture inputs.
    3. Compares concrete (non-placeholder) field values between the doc example
       and the runtime result using ``_collect_drifts``.

    A failure indicates that either the documentation or the implementation is
    out of sync.  A maintainer must explicitly reconcile the difference.
    """

    # ------------------------------------------------------------------
    # Fixtures
    # ------------------------------------------------------------------

    @pytest.fixture(scope="class")
    def doc_scenarios(self) -> dict[str, dict[str, Any]]:
        """Parse and cache all §4.x JSON examples from the contract doc."""
        return _parse_section_json_from_doc()

    @pytest.fixture(scope="class")
    def doc_section_ids(self) -> set[str]:
        """All ``### 4.x`` section IDs present in the contract document."""
        return _find_doc_section_ids()

    # ------------------------------------------------------------------
    # Structural integrity checks
    # ------------------------------------------------------------------

    def test_doc_has_all_fixture_sections(self, doc_section_ids: set[str]) -> None:
        """Every section in ``_SECTION_FIXTURES`` must exist in the contract doc.

        Fails when a fixture references a section that was renamed or removed
        from the document, preventing ghost fixtures from silently passing.
        """
        missing_from_doc = frozenset(_SECTION_FIXTURES) - doc_section_ids
        assert not missing_from_doc, (
            f"Sections in _SECTION_FIXTURES not found in the contract doc "
            f"({_CONTRACT_DOC_PATH.name}): "
            + ", ".join(f"§{s}" for s in sorted(missing_from_doc))
        )

    def test_all_doc_sections_are_mapped_or_excluded(
        self, doc_section_ids: set[str]
    ) -> None:
        """Every ``### 4.x`` section in the doc must be in ``_SECTION_FIXTURES``
        or explicitly listed in ``_EXCLUDED_SECTIONS``.

        Fails when a new §4.x section is added to the contract doc without a
        corresponding fixture or an explicit exclusion note, ensuring no scenario
        can accumulate silently without coverage.
        """
        unmapped = (
            doc_section_ids
            - frozenset(_SECTION_FIXTURES)
            - frozenset(_EXCLUDED_SECTIONS)
        )
        assert not unmapped, (
            f"Doc sections {[f'§{s}' for s in sorted(unmapped, key=lambda s: tuple(int(p) for p in s.split('.')))]} "
            f"have no entry in _SECTION_FIXTURES and no exclusion note in "
            f"_EXCLUDED_SECTIONS. Add the scenario fixture or document why "
            f"automated comparison is not possible in _EXCLUDED_SECTIONS."
        )

    # ------------------------------------------------------------------
    # Per-section drift checks
    # ------------------------------------------------------------------

    @pytest.mark.parametrize("section_id", sorted(_SECTION_FIXTURES))
    def test_no_drift_between_doc_and_runtime(
        self,
        section_id: str,
        doc_scenarios: dict[str, dict[str, Any]],
    ) -> None:
        """Concrete field values in the §{section_id} doc example must match
        the live ``run_retrieval_and_qa()`` output.

        A failure means the documented scenario and the runtime behaviour have
        diverged.  Inspect the drift messages to determine whether the doc or
        the implementation needs to be updated.
        """
        doc_json = doc_scenarios.get(section_id)
        if doc_json is None:
            pytest.fail(
                f"§{section_id} is listed in _SECTION_FIXTURES but has no JSON "
                f"code block in the contract doc ({_CONTRACT_DOC_PATH.name}). "
                f"Either add a JSON example to the doc section or remove the "
                f"entry from _SECTION_FIXTURES."
            )

        runtime_result = _run_with_mocked_retrieval(**_SECTION_FIXTURES[section_id])
        drifts = _collect_drifts(section_id, doc_json, runtime_result)

        assert not drifts, (
            f"Doc-vs-runtime drift detected in §{section_id} "
            f"({_CONTRACT_DOC_PATH.name}):\n"
            + "\n".join(f"  • {d}" for d in drifts)
        )
