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
    Parametrized end-to-end drift checks for §4 (live postprocessed) scenarios.

    - ``test_doc_has_all_fixture_sections`` — every section ID in
      ``_SECTION_FIXTURES`` must be present as a ``### 4.x`` heading in the doc.
    - ``test_all_doc_sections_are_mapped_or_excluded`` — every ``### 4.x`` heading
      in the doc is either in ``_SECTION_FIXTURES`` or explicitly noted in
      ``_EXCLUDED_SECTIONS`` so nothing falls through silently.
    - ``test_no_drift_between_doc_and_runtime[4.x]`` — for each mapped section,
      concrete (non-placeholder) field values from the doc JSON must match the
      live runtime output.

``TestDocEarlyReturnDrift``
    Parametrized end-to-end drift checks for §5 (early-return) scenarios.

    - ``test_doc_has_all_early_return_fixture_sections`` — every section ID in
      ``_EARLY_RETURN_SECTION_RUNNERS`` must be present as a ``### 5.x`` heading.
    - ``test_all_early_return_doc_sections_are_mapped_or_excluded`` — every
      ``### 5.x`` heading is either in ``_EARLY_RETURN_SECTION_RUNNERS`` or in
      ``_EXCLUDED_EARLY_RETURN_SECTIONS``.
    - ``test_no_drift_between_doc_and_runtime[5.x]`` — for each mapped section,
      concrete field values from the doc JSON must match the live runtime output.
"""
from __future__ import annotations

import json
import re
import types
from pathlib import Path
from typing import Any, Callable

import pytest
import yaml

from demo.stages.retrieval_and_qa import _CITATION_FALLBACK_PREFIX, run_retrieval_and_qa
from demo.tests.test_retrieval_result_contract import (
    _CITED_ANSWER,
    _DRY_RUN_CONFIG,
    _EMPTY_CHUNK_METADATA,
    _LIVE_ITEM_METADATA,
    _UNCITED_ANSWER,
    _run_with_mocked_retrieval,
)

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
# Canonical fixture file
# ---------------------------------------------------------------------------

#: Path to the machine-readable canonical scenario fixture file used by the
#: doc-vs-runtime drift checks in this module. The runtime contract tests in
#: ``test_retrieval_result_contract.py`` mirror these scenarios via Python
#: constants and integrity checks rather than loading this YAML directly.
_FIXTURE_PATH: Path = Path(__file__).parent / "contract_fixtures" / "retrieval_citation_scenarios.yaml"


def _load_contract_scenarios() -> dict[str, Any]:
    """Load and return the parsed contents of the canonical fixture YAML file.

    Raises
    ------
    FileNotFoundError
        If the fixture file does not exist at ``_FIXTURE_PATH``.
    ValueError
        If the parsed YAML content is not a mapping/dict.
    """
    data = yaml.safe_load(_FIXTURE_PATH.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(
            f"Expected a mapping at {_FIXTURE_PATH}, but got {type(data).__name__!r}"
        )
    return data


def _build_section_fixtures(
    scenarios_data: dict[str, Any],
) -> dict[str, dict[str, Any]]:
    """Build the section-to-kwargs mapping for ``_run_with_mocked_retrieval``.

    Only non-excluded ``live_scenarios`` entries are included.  Each entry's
    ``answer``, ``items_metadata``, ``all_runs``, and (optionally) ``run_id``
    fields are forwarded verbatim to ``_run_with_mocked_retrieval``.

    Raises
    ------
    ValueError
        If a non-excluded scenario is missing a required field so that the
        error is caught by the import-time try/except and surfaces via the
        integrity tests rather than as a raw ``KeyError``.
    """
    result: dict[str, dict[str, Any]] = {}
    for section_id, scenario in scenarios_data.get("live_scenarios", {}).items():
        if not isinstance(scenario, dict):
            raise ValueError(
                f"Live scenario {section_id!r} is not a mapping (got {type(scenario).__name__!r})"
            )
        if scenario.get("excluded", False):
            continue
        for required in ("answer", "items_metadata", "all_runs"):
            if required not in scenario:
                raise ValueError(
                    f"Live scenario {section_id!r} is missing required field {required!r}"
                )
        params: dict[str, Any] = {
            "answer": scenario["answer"],
            "items_metadata": scenario["items_metadata"],
            "all_runs": scenario["all_runs"],
        }
        if "run_id" in scenario:
            params["run_id"] = scenario["run_id"]
        result[section_id] = params
    return result


def _build_excluded_sections(
    scenarios_data: dict[str, Any],
) -> dict[str, str]:
    """Return the ``excluded_reason`` strings for excluded ``live_scenarios`` entries.

    Raises
    ------
    ValueError
        If ``live_scenarios`` is not a mapping or any scenario entry is not a
        mapping, so that malformed fixtures surface with a clear error message
        rather than as ``AttributeError``/``TypeError``.
    """
    live_scenarios = scenarios_data.get("live_scenarios", {})
    if not isinstance(live_scenarios, dict):
        raise ValueError(
            "Expected 'live_scenarios' to be a mapping/dict, but got "
            f"{type(live_scenarios).__name__!r}"
        )

    result: dict[str, str] = {}
    for section_id, scenario in live_scenarios.items():
        if not isinstance(scenario, dict):
            raise ValueError(
                "Expected each 'live_scenarios' entry to be a mapping/dict, "
                f"but section {section_id!r} has type {type(scenario).__name__!r}"
            )
        if scenario.get("excluded", False):
            if "excluded_reason" not in scenario:
                raise ValueError(
                    "Excluded scenario {section_id!r} is missing required "
                    "'excluded_reason' field"
                )
            result[section_id] = scenario["excluded_reason"]

    return result
def _make_early_return_runner(
    section_id: str,
    scenario: dict[str, Any],
) -> Callable[[], dict[str, Any]]:
    """Build a zero-argument callable that executes the early-return scenario.

    Parameters
    ----------
    section_id:
        The section key (e.g. ``"5.1"``) used in error messages.
    scenario:
        A single ``early_return_scenarios`` entry from the fixture file.
        Must contain ``run_id`` (str) and ``dry_run`` (bool).  For non-dry-run
        scenarios the ``question`` key must also be present (explicitly set to
        ``null`` to trigger the retrieval-skipped path, or a string to pass a
        concrete question).

    Returns
    -------
    Callable
        A zero-argument function that calls ``run_retrieval_and_qa()`` with
        the appropriate config and returns the result dict.

    Raises
    ------
    ValueError
        If ``scenario`` is not a mapping, or if a required field
        (``run_id``, ``dry_run``, or ``question`` for non-dry-run scenarios)
        is missing so the error is meaningful.
    """
    if not isinstance(scenario, dict):
        raise ValueError(
            f"Early-return scenario {section_id!r} is not a mapping "
            f"(got {type(scenario).__name__!r})"
        )
    for required in ("run_id", "dry_run"):
        if required not in scenario:
            raise ValueError(
                f"Early-return scenario {section_id!r} is missing required field {required!r}"
            )

    run_id: str = scenario["run_id"]

    if scenario["dry_run"]:
        def _dry_run_runner() -> dict[str, Any]:
            return run_retrieval_and_qa(_DRY_RUN_CONFIG, run_id=run_id, source_uri=None)

        return _dry_run_runner

    # Retrieval-skipped path: live config with empty Neo4j credentials and
    # question=None so the function short-circuits before opening a driver.
    # Require explicit null in the fixture; a missing key raises ValueError
    # with context rather than silently becoming None and triggering an
    # unintended early return.
    if "question" not in scenario:
        raise ValueError(
            f"Early-return scenario {section_id!r} is non-dry-run but missing "
            f"required field 'question' (set to null to trigger the skipped path)"
        )
    question: str | None = scenario["question"]

    def _skip_runner() -> dict[str, Any]:
        return run_retrieval_and_qa(
            types.SimpleNamespace(
                dry_run=False,
                openai_model="gpt-4o-mini",
                neo4j_uri="",
                neo4j_username="",
                neo4j_password="",
                neo4j_database=None,
            ),
            run_id=run_id,
            source_uri=None,
            question=question,
        )

    return _skip_runner


def _build_early_return_runners(
    scenarios_data: dict[str, Any],
) -> dict[str, Callable[[], dict[str, Any]]]:
    """Build the section-to-runner mapping for early-return (§5.x) scenarios.

    Only non-excluded ``early_return_scenarios`` entries are included.
    """
    early_return_scenarios = scenarios_data.get("early_return_scenarios", {})
    if not isinstance(early_return_scenarios, dict):
        raise ValueError("early_return_scenarios must be a mapping")

    runners: dict[str, Callable[[], dict[str, Any]]] = {}
    for section_id, scenario in early_return_scenarios.items():
        if not isinstance(scenario, dict):
            raise ValueError(
                f"early_return_scenarios[{section_id!r}] must be a mapping"
            )
        if scenario.get("excluded", False):
            continue
        runners[section_id] = _make_early_return_runner(section_id, scenario)

    return runners


def _build_excluded_early_return_sections(
    scenarios_data: dict[str, Any],
) -> dict[str, str]:
    """Return excluded_reason strings for excluded ``early_return_scenarios`` entries."""
    early_return_scenarios = scenarios_data.get("early_return_scenarios", {})
    if not isinstance(early_return_scenarios, dict):
        raise ValueError("early_return_scenarios must be a mapping")

    excluded_sections: dict[str, str] = {}
    for section_id, scenario in early_return_scenarios.items():
        if not isinstance(scenario, dict):
            raise ValueError(
                f"early_return_scenarios[{section_id!r}] must be a mapping"
            )
        if scenario.get("excluded", False):
            excluded_sections[section_id] = scenario["excluded_reason"]

    return excluded_sections
# Load the fixture file once at import time so the resulting dicts can be used
# in parametrize decorators (which are evaluated at collection time).  If the
# file is missing or malformed the load is silenced here so that test collection
# still succeeds; TestContractFixtureIntegrity.test_fixture_file_exists /
# test_fixture_file_is_loadable will then fail with a clear, actionable message
# rather than an opaque import-time traceback.
#
# All four scenario dicts are built inside the same guarded block so that
# validation errors from the builder functions (missing required fields, wrong
# scenario shape, missing excluded_reason, etc.) are also captured in
# ``_SCENARIOS_DATA_ERROR`` rather than escaping as opaque import-time exceptions.
try:
    _SCENARIOS_DATA: dict[str, Any] = _load_contract_scenarios()
    _SECTION_FIXTURES: dict[str, dict[str, Any]] = _build_section_fixtures(_SCENARIOS_DATA)
    _EXCLUDED_SECTIONS: dict[str, str] = _build_excluded_sections(_SCENARIOS_DATA)
    _EARLY_RETURN_SECTION_RUNNERS: dict[str, Callable[[], dict[str, Any]]] = (
        _build_early_return_runners(_SCENARIOS_DATA)
    )
    _EXCLUDED_EARLY_RETURN_SECTIONS: dict[str, str] = _build_excluded_early_return_sections(
        _SCENARIOS_DATA
    )
    _SCENARIOS_DATA_ERROR: Exception | None = None
except Exception as exc:  # pragma: no cover - exercised indirectly via integrity tests
    # Preserve test collection even if the fixture file is missing, malformed,
    # or a builder function raises due to an invalid scenario entry.
    # TestContractFixtureIntegrity will then fail with an actionable message.
    _SCENARIOS_DATA = {}
    _SECTION_FIXTURES = {}
    _EXCLUDED_SECTIONS = {}
    _EARLY_RETURN_SECTION_RUNNERS = {}
    _EXCLUDED_EARLY_RETURN_SECTIONS = {}
    _SCENARIOS_DATA_ERROR = exc

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


def _parse_early_return_section_json_from_doc() -> dict[str, dict[str, Any]]:
    """Parse JSON examples from §5.x subsections of the contract document.

    Returns
    -------
    dict[str, dict]
        Mapping of section number (e.g. ``"5.1"``) to the parsed JSON dict.
        Sections that contain no JSON code block are omitted.

    Raises
    ------
    FileNotFoundError
        If the contract document does not exist at ``_CONTRACT_DOC_PATH``.
    ValueError
        If a JSON code block in a §5.x section cannot be parsed.
    """
    text = _CONTRACT_DOC_PATH.read_text(encoding="utf-8")

    # Each ### 5.x heading starts a subsection; body runs until the next heading.
    section_re = re.compile(
        r"^### (5\.\d+)[^\n]*\n(.*?)(?=^### |^## |\Z)",
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


def _find_early_return_doc_section_ids() -> set[str]:
    """Return all ``### 5.x`` section IDs found in the contract document."""
    text = _CONTRACT_DOC_PATH.read_text(encoding="utf-8")
    return set(re.findall(r"^### (5\.\d+)", text, re.MULTILINE))

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

       * Fields in ``_ANSWER_TEXT_FIELDS``: type check (must be ``str``), plus
         a prefix check when ``citation_fallback_applied`` is ``True`` in the
         same dict — the runtime value must start with
         ``_CITATION_FALLBACK_PREFIX``.
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
            # Require the runtime value to be a real int (bools are not accepted,
            # even though they are subclasses of int).
            if not isinstance(rt_val, int) or isinstance(rt_val, bool):
                drifts.append(
                    f"[§{section_id}] {field_path!r}:"
                    f" doc has int, runtime has {type(rt_val).__name__!r}"
                )
            elif doc_val != rt_val:
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
                # Answer text in the contract doc is largely illustrative. We
                # require the runtime value to be a string and, when
                # citation_fallback_applied is True at the same dict level, we
                # also require the public `answer` (not `raw_answer`) to start
                # with the documented fallback prefix so drift in that prefix
                # is still caught.
                if not isinstance(rt_val, str):
                    drifts.append(
                        f"[§{section_id}] {field_path!r}:"
                        f" doc has str, runtime has {type(rt_val).__name__!r}"
                    )
                elif (
                    leaf == "answer"
                    and doc.get("citation_fallback_applied") is True
                    and not rt_val.startswith(_CITATION_FALLBACK_PREFIX)
                ):
                    drifts.append(
                        f"[§{section_id}] {field_path!r}:"
                        f" citation_fallback_applied is True but runtime answer"
                        f" does not start with {_CITATION_FALLBACK_PREFIX!r}"
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
# Section-to-fixture mapping
# ---------------------------------------------------------------------------
# ``_SECTION_FIXTURES`` and ``_EXCLUDED_SECTIONS`` are both populated in the
# guarded try/except block near the top of this module (after all builder
# function definitions) so that any validation error from the builders is
# captured in ``_SCENARIOS_DATA_ERROR`` rather than escaping at import time.
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# Test class
# ---------------------------------------------------------------------------


@pytest.mark.skipif(
    _SCENARIOS_DATA_ERROR is not None,
    reason="Skipping §4.x drift tests because the scenarios fixture failed to load; "
    "see TestContractFixtureIntegrity for the actionable failure.",
)
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

    @pytest.mark.parametrize(
        "section_id",
        sorted(
            _SECTION_FIXTURES,
            key=lambda s: tuple(int(part) for part in s.split(".")),
        ),
    )
    def test_no_drift_between_doc_and_runtime(
        self,
        section_id: str,
        doc_scenarios: dict[str, dict[str, Any]],
    ) -> None:
        """Concrete field values in the doc example for this section must match
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


# ---------------------------------------------------------------------------
# Early-return (§5.x) section runners and fixtures
# ---------------------------------------------------------------------------
# ``_EARLY_RETURN_SECTION_RUNNERS`` and ``_EXCLUDED_EARLY_RETURN_SECTIONS`` are
# both populated in the guarded try/except block near the top of this module
# so that any validation error from the builders is captured in
# ``_SCENARIOS_DATA_ERROR`` rather than escaping at import time.
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# Early-return drift test class
# ---------------------------------------------------------------------------


@pytest.mark.skipif(
    _SCENARIOS_DATA_ERROR is not None,
    reason="Skipping §5.x early-return drift tests because the scenarios fixture failed "
    "to load; see TestContractFixtureIntegrity for the actionable failure.",
)
class TestDocEarlyReturnDrift:
    """Detect drift between §5 (early-return) JSON examples in the contract doc
    and live runtime output.

    For each §5.x section mapped in ``_EARLY_RETURN_SECTION_RUNNERS`` this class:

    1. Reads the JSON example directly from the contract markdown document.
    2. Calls the runner callable to obtain the runtime result.
    3. Compares concrete (non-placeholder) field values using ``_collect_drifts``.

    A failure indicates that either the documentation or the implementation is
    out of sync.  A maintainer must explicitly reconcile the difference.
    """

    @pytest.fixture(scope="class")
    def early_return_doc_scenarios(self) -> dict[str, dict[str, Any]]:
        """Parse and cache all §5.x JSON examples from the contract doc."""
        return _parse_early_return_section_json_from_doc()

    @pytest.fixture(scope="class")
    def early_return_doc_section_ids(self) -> set[str]:
        """All ``### 5.x`` section IDs present in the contract document."""
        return _find_early_return_doc_section_ids()

    def test_doc_has_all_early_return_fixture_sections(
        self, early_return_doc_section_ids: set[str]
    ) -> None:
        """Every section in ``_EARLY_RETURN_SECTION_RUNNERS`` must exist in the doc.

        Fails when a runner references a section that was renamed or removed.
        """
        missing_from_doc = frozenset(_EARLY_RETURN_SECTION_RUNNERS) - early_return_doc_section_ids
        assert not missing_from_doc, (
            f"Sections in _EARLY_RETURN_SECTION_RUNNERS not found in the contract doc "
            f"({_CONTRACT_DOC_PATH.name}): "
            + ", ".join(f"§{s}" for s in sorted(missing_from_doc))
        )

    def test_all_early_return_doc_sections_are_mapped_or_excluded(
        self, early_return_doc_section_ids: set[str]
    ) -> None:
        """Every ``### 5.x`` heading in the doc must be in ``_EARLY_RETURN_SECTION_RUNNERS``
        or explicitly listed in ``_EXCLUDED_EARLY_RETURN_SECTIONS``.

        Fails when a new §5.x section is added to the doc without coverage.
        """
        unmapped = (
            early_return_doc_section_ids
            - frozenset(_EARLY_RETURN_SECTION_RUNNERS)
            - frozenset(_EXCLUDED_EARLY_RETURN_SECTIONS)
        )
        assert not unmapped, (
            f"Doc sections {[f'§{s}' for s in sorted(unmapped, key=lambda s: tuple(int(p) for p in s.split('.')))]} "
            f"have no entry in _EARLY_RETURN_SECTION_RUNNERS and no exclusion note. "
            f"Add a runner or document why automated comparison is not possible in "
            f"_EXCLUDED_EARLY_RETURN_SECTIONS."
        )

    @pytest.mark.parametrize(
        "section_id",
        sorted(
            _EARLY_RETURN_SECTION_RUNNERS,
            key=lambda s: tuple(int(part) for part in s.split(".")),
        ),
    )
    def test_no_drift_between_doc_and_runtime(
        self,
        section_id: str,
        early_return_doc_scenarios: dict[str, dict[str, Any]],
    ) -> None:
        """Concrete field values in the §5.x doc example must match the runtime output.

        A failure means the documented early-return scenario and the runtime
        behaviour have diverged.  Inspect the drift messages to determine whether
        the doc or the implementation needs to be updated.
        """
        doc_json = early_return_doc_scenarios.get(section_id)
        if doc_json is None:
            pytest.fail(
                f"§{section_id} is listed in _EARLY_RETURN_SECTION_RUNNERS but has "
                f"no JSON code block in the contract doc ({_CONTRACT_DOC_PATH.name}). "
                f"Either add a JSON example to the doc section or remove the entry "
                f"from _EARLY_RETURN_SECTION_RUNNERS."
            )

        runtime_result = _EARLY_RETURN_SECTION_RUNNERS[section_id]()
        drifts = _collect_drifts(section_id, doc_json, runtime_result)

        assert not drifts, (
            f"Doc-vs-runtime drift detected in §{section_id} "
            f"({_CONTRACT_DOC_PATH.name}):\n"
            + "\n".join(f"  • {d}" for d in drifts)
        )


# ---------------------------------------------------------------------------
# Fixture integrity checks
# ---------------------------------------------------------------------------


class TestContractFixtureIntegrity:
    """Verify that the canonical fixture file is internally consistent and
    stays aligned with the shared constants in ``test_retrieval_result_contract``.

    These tests act as a coupling mechanism: if a maintainer changes a shared
    constant in the runtime contract test (e.g. ``_CITED_ANSWER``) without
    updating the fixture file, or vice versa, a failure here makes the
    discrepancy visible before any drift tests run.
    """

    def _require_scenarios_data(self) -> None:
        """Fail with a clear message if the fixture file could not be loaded.

        Call at the start of any test that accesses ``_SCENARIOS_DATA``.
        """
        if _SCENARIOS_DATA_ERROR is not None:
            pytest.fail(
                f"Fixture file at {_FIXTURE_PATH} could not be loaded; "
                f"fix the file before running these tests.\n"
                f"  Error: {_SCENARIOS_DATA_ERROR}"
            )

    def test_fixture_file_exists(self) -> None:
        """The canonical fixture YAML file must exist at ``_FIXTURE_PATH``."""
        assert _FIXTURE_PATH.exists(), (
            f"Canonical fixture file not found at {_FIXTURE_PATH}. "
            "Create it or update _FIXTURE_PATH."
        )

    def test_fixture_file_is_loadable(self) -> None:
        """The fixture file must parse without errors and produce a mapping.

        Also surfaces any import-time load error so the failure message is
        actionable even when this test runs first in the session.
        """
        self._require_scenarios_data()
        data = _load_contract_scenarios()
        assert "live_scenarios" in data, "Fixture file must have a 'live_scenarios' key"
        assert "early_return_scenarios" in data, (
            "Fixture file must have an 'early_return_scenarios' key"
        )
        assert "shared" in data, "Fixture file must have a 'shared' key"

    def test_fixture_cited_answer_matches_test_constant(self) -> None:
        """``shared.cited_answer`` in the fixture must equal ``_CITED_ANSWER``
        from ``test_retrieval_result_contract``.

        Fails if the runtime test constant and the fixture file drift apart,
        ensuring that both sources drive the same scenarios.
        """
        self._require_scenarios_data()
        fixture_cited = _SCENARIOS_DATA["shared"]["cited_answer"]
        assert fixture_cited == _CITED_ANSWER, (
            f"Fixture shared.cited_answer does not match _CITED_ANSWER.\n"
            f"  fixture : {fixture_cited!r}\n"
            f"  constant: {_CITED_ANSWER!r}"
        )

    def test_fixture_uncited_answer_matches_test_constant(self) -> None:
        """``shared.uncited_answer`` in the fixture must equal ``_UNCITED_ANSWER``."""
        self._require_scenarios_data()
        fixture_uncited = _SCENARIOS_DATA["shared"]["uncited_answer"]
        assert fixture_uncited == _UNCITED_ANSWER, (
            f"Fixture shared.uncited_answer does not match _UNCITED_ANSWER.\n"
            f"  fixture : {fixture_uncited!r}\n"
            f"  constant: {_UNCITED_ANSWER!r}"
        )

    def test_fixture_live_item_metadata_matches_test_constant(self) -> None:
        """``shared.live_item_metadata`` in the fixture must equal ``_LIVE_ITEM_METADATA``."""
        self._require_scenarios_data()
        fixture_meta = _SCENARIOS_DATA["shared"]["live_item_metadata"]
        assert fixture_meta == _LIVE_ITEM_METADATA, (
            f"Fixture shared.live_item_metadata does not match _LIVE_ITEM_METADATA.\n"
            f"  fixture : {fixture_meta!r}\n"
            f"  constant: {_LIVE_ITEM_METADATA!r}"
        )

    def test_fixture_empty_chunk_metadata_matches_test_constant(self) -> None:
        """``shared.empty_chunk_metadata`` in the fixture must equal ``_EMPTY_CHUNK_METADATA``."""
        self._require_scenarios_data()
        fixture_meta = _SCENARIOS_DATA["shared"]["empty_chunk_metadata"]
        assert fixture_meta == _EMPTY_CHUNK_METADATA, (
            f"Fixture shared.empty_chunk_metadata does not match _EMPTY_CHUNK_METADATA.\n"
            f"  fixture : {fixture_meta!r}\n"
            f"  constant: {_EMPTY_CHUNK_METADATA!r}"
        )

    def test_fixture_live_scenarios_keys_match_section_fixtures(self) -> None:
        """Every non-excluded live scenario in the fixture file must appear in
        ``_SECTION_FIXTURES``, and every entry in ``_SECTION_FIXTURES`` must
        correspond to a non-excluded live scenario in the fixture file.
        """
        self._require_scenarios_data()
        fixture_active = frozenset(
            sid
            for sid, s in _SCENARIOS_DATA["live_scenarios"].items()
            if not s.get("excluded", False)
        )
        assert fixture_active == frozenset(_SECTION_FIXTURES), (
            f"Non-excluded live fixture sections do not match _SECTION_FIXTURES.\n"
            f"  in fixture only : {sorted(fixture_active - frozenset(_SECTION_FIXTURES))}\n"
            f"  in _SECTION_FIXTURES only: {sorted(frozenset(_SECTION_FIXTURES) - fixture_active)}"
        )

    def test_fixture_early_return_keys_match_runners(self) -> None:
        """Every non-excluded early-return scenario in the fixture file must
        appear in ``_EARLY_RETURN_SECTION_RUNNERS``, and every runner must have
        a corresponding fixture entry.
        """
        self._require_scenarios_data()
        fixture_active = frozenset(
            sid
            for sid, s in _SCENARIOS_DATA["early_return_scenarios"].items()
            if not s.get("excluded", False)
        )
        assert fixture_active == frozenset(_EARLY_RETURN_SECTION_RUNNERS), (
            f"Non-excluded early-return fixture sections do not match "
            f"_EARLY_RETURN_SECTION_RUNNERS.\n"
            f"  in fixture only : {sorted(fixture_active - frozenset(_EARLY_RETURN_SECTION_RUNNERS))}\n"
            f"  in _EARLY_RETURN_SECTION_RUNNERS only: "
            f"{sorted(frozenset(_EARLY_RETURN_SECTION_RUNNERS) - fixture_active)}"
        )
