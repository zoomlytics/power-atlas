# Power Atlas — Retrieval/Citation Result Contract (v0.1)

**Status:** Accepted  
**Audience:** Contributors, architects, reviewers  
**Scope:** Postprocessing semantics for the retrieval/citation result dict in **postprocessed `status="live"` results** from `run_retrieval_and_qa` (i.e., runs where QA executed and `_postprocess_answer` ran to completion).

---

## 1) Summary

`run_retrieval_and_qa` returns a result dict that contains both the **final deliverable fields** (what callers and the UI consume) and **diagnostic fields** (what tests and observability tooling inspect).  The postprocessing path — citation repair, citation fallback, evidence-level derivation — runs through a single shared helper (`_postprocess_answer`) so the single-shot and interactive paths stay aligned for **live, postprocessed runs**.

This document is the canonical reference for the meaning, relationships, and invariants of every postprocessing/result field **in postprocessed `status="live"` payloads**.  It is not a description of the retrieval architecture itself (see [retrieval-semantics-v0.1.md](retrieval-semantics-v0.1.md)); it focuses exclusively on what the postprocessed result dict carries and why.  **Dry-run and other early-return result shapes (e.g., `status="dry_run"`) are out of scope and may omit postprocessing-only fields such as `warnings`.**

---

## 2) Field Definitions

### 2.1 Raw answer fields

| Field | Type | Description |
|---|---|---|
| `raw_answer` | `str` | Original LLM output before any repair or fallback prefix is applied. |
| `raw_answer_all_cited` | `bool` | `True` when every sentence/bullet in `raw_answer` ends with a `[CITATION|…]` token. Computed before repair runs. |

`raw_answer` is always the unmodified LLM text.  Even when the delivered answer is completely different (e.g. a fallback prefix was prepended), `raw_answer` preserves the original LLM output for audit and diagnostic purposes.

### 2.2 Citation repair fields

| Field | Type | Description |
|---|---|---|
| `citation_repair_attempted` | `bool` | `True` when the preconditions for repair were met and repair logic was entered, regardless of whether repair ultimately changed the answer. `False` when repair was never evaluated (e.g. not in all-runs mode, answer already fully cited, no hits available). |
| `citation_repair_applied` | `bool` | `True` **only** when repair logic ran *and* the answer text actually changed as a result. |
| `citation_repair_strategy` | `str \| None` | Name of the repair algorithm used (e.g. `"append_first_retrieved_token"`), or `None` when `citation_repair_applied` is `False`. |
| `citation_repair_source_chunk_id` | `str \| None` | `chunk_id` of the retrieved chunk whose citation token was used during repair, or `None` when `citation_repair_applied` is `False` **or when the winning retrieved hit had no `chunk_id` to propagate**. |

**Repair invariants:**

- `citation_repair_attempted` reflects whether repair logic was **entered** (preconditions met), not whether repair ultimately changed anything.
- `citation_repair_applied` reflects whether the **answer text changed**, not merely whether repair logic was invoked.  If repair ran but produced a string identical to the input, `citation_repair_applied` is `False`.
- `citation_repair_strategy` is **only populated when `citation_repair_applied` is `True`**. `citation_repair_source_chunk_id` is populated when `citation_repair_applied` is `True` **and** the selected retrieved hit exposes a non-empty `chunk_id`; otherwise it is `None`. When `citation_repair_applied` is `False`, both are `None`.
- `citation_repair_applied` implies `citation_repair_attempted`: if `citation_repair_applied` is `True`, then `citation_repair_attempted` is also `True`.  The reverse is not true: `citation_repair_attempted` can be `True` while `citation_repair_applied` is `False` (repair was entered but produced no change or found no candidate token).
- Repair is currently only attempted in **all-runs mode** (`all_runs=True`), because that mode lacks a single authoritative `run_id` citation token and the LLM sometimes omits trailing tokens.

### 2.3 Final answer fields

| Field | Type | Description |
|---|---|---|
| `answer` | `str` | **Primary deliverable.**  The `display_answer` from postprocessing: the repaired answer text with a fallback prefix prepended when not all sentences/bullets are cited. |
| `all_answers_cited` | `bool` | `True` when every sentence/bullet in the **final delivered answer** (after repair; before fallback prefix) ends with a citation token. |
| `citation_fallback_applied` | `bool` | `True` when the fallback prefix `"Insufficient citations detected: …"` was prepended to the answer. |

**`answer` vs `raw_answer`:**

`answer` (= `display_answer`) is what callers and the UI show.  It differs from `raw_answer` when:
1. Citation repair was applied (the repaired text replaces the raw text), **and/or**
2. The fallback prefix was prepended (because the answer — whether raw or repaired — was not fully cited).

### 2.4 Display-answer vs history-answer semantics

Two answer variants are produced internally by `_postprocess_answer`:

| Internal key | Exposed as | Purpose |
|---|---|---|
| `display_answer` | `answer` in result dict | Shown to the user; includes the fallback prefix when citations are incomplete. |
| `history_answer` | Used only in interactive mode | Stored in conversation history.  When the fallback prefix was applied, only the bare prefix string is stored — not the full under-cited output — so subsequent turns are not conditioned on low-quality evidence. |

`history_answer` is **not** included in the `run_retrieval_and_qa` result dict; it is used exclusively by `run_interactive_qa` when writing to the conversation `MessageHistory`.

### 2.5 Citation quality fields

| Field | Type | Description |
|---|---|---|
| `citation_quality` | `dict` | Structured citation-quality bundle (see §2.5.1). |
| `citation_warnings` | `list[str]` (inside `citation_quality`) | All citation-quality warnings for this result. |
| `warnings` | `list[str]` | Broader operational warnings list (superset of some `citation_warnings`). |
| `evidence_level` | `str` (inside `citation_quality`) | `"no_answer"`, `"full"`, or `"degraded"`. |

#### 2.5.1 `citation_quality` bundle fields

| Field | Type | Description |
|---|---|---|
| `all_cited` | `bool` | Whether every sentence/bullet in the final answer is cited.  Mirrors `all_answers_cited` at the top level. |
| `raw_answer_all_cited` | `bool` | Whether the raw LLM output was fully cited before any repair.  Mirrors `raw_answer_all_cited` at the top level. |
| `evidence_level` | `"no_answer" \| "full" \| "degraded"` | Encodes overall citation quality (see §2.8). |
| `warning_count` | `int` | `len(citation_warnings)`. |
| `citation_warnings` | `list[str]` | All citation-quality warnings, including warnings that were raised before postprocessing (e.g. empty-chunk-text warnings). |

#### 2.5.2 `warnings` vs `citation_warnings`

`warnings` is the **top-level operational warnings list** returned in the result dict.  It is a superset:

- It contains every warning that was also added to `citation_warnings` (e.g. the uncited-answer warning, the empty-chunk-text warning).
- It may also contain additional operational warnings that are **not** citation-quality issues (e.g. the `"No question provided; skipping vector retrieval."` warning).

`citation_warnings` (inside `citation_quality`) contains **only citation-quality-related** warnings.  Callers that want to assess citation quality specifically should use `citation_quality["citation_warnings"]`; callers that want all warnings should use the top-level `warnings` list.

### 2.7 Malformed-diagnostics telemetry

| Field | Type | Description |
|---|---|---|
| `malformed_diagnostics_count` | `int` | Number of retrieved hits whose `retrieval_path_diagnostics` payload failed at least one structural check during result formatting.  Zero when all hits have well-formed (or absent/`None`) diagnostics. |

A hit contributes to `malformed_diagnostics_count` (at most once, regardless of how many sub-field errors it has) when its `retrieval_path_diagnostics` value is **present and not `None`** but:

- The root value is not a `dict`, **or**
- Any known list field (`has_participant_edges`, `canonical_via_resolves_to`, `cluster_memberships`, `cluster_canonical_via_aligned_with`) is present with a non-`None` value that is not a `list`, **or**
- Any entry in `has_participant_edges`, `cluster_memberships`, or `cluster_canonical_via_aligned_with` is not a `dict`, **or**
- Any `roles` entry within an `has_participant_edges` element is present with a non-`None` value that is not a `list`, or contains a non-`dict` item. (`roles=None` is treated as absent.)

Hits where `retrieval_path_diagnostics` is **absent or `None`** are **not** counted — they represent an older result format rather than a data error.

`malformed_diagnostics_count > 0` is a signal for downstream alerting: it indicates that the graph database returned diagnostics payloads with unexpected types, which may reflect a schema migration, a bug in the retrieval query, or data corruption.  The human-readable `retrieval_path_summary` string surfaces per-hit details, while `malformed_diagnostics_count` provides a machine-readable counter for metrics and alerting without requiring string parsing.

### 2.8 Evidence-level semantics

`evidence_level` is derived from `all_cited` (for the final answer) and the combined `citation_warnings` list:

| Value | Condition |
|---|---|
| `"no_answer"` | Answer text is empty or whitespace-only after repair. |
| `"full"` | Every sentence/bullet is cited **and** `citation_warnings` is empty. |
| `"degraded"` | Any sentence/bullet is missing a citation token **or** any citation-quality warning exists. |

`evidence_level` reflects the state of the **repaired answer**, not the raw LLM output.  An answer that was not fully cited in `raw_answer` but was repaired to full citation by `citation_repair_applied=True` will still show `"full"` if `citation_warnings` is empty after repair.

---

## 3) Field Invariants

The following invariants hold across all postprocessing paths:

1. **Repair-applied invariant:** `citation_repair_strategy` is `None` whenever `citation_repair_applied` is `False`. `citation_repair_source_chunk_id` is `None` whenever `citation_repair_applied` is `False`, and may also be `None` when `citation_repair_applied` is `True` if the winning retrieved hit had no `chunk_id`.

2. **Text-change invariant:** `citation_repair_applied = True` means the repaired answer text *differs* from `raw_answer`.  If repair ran but produced identical text, `citation_repair_applied` remains `False`.

3. **Attempted ⊇ applied invariant:** `citation_repair_applied = True` implies `citation_repair_attempted = True`.  The reverse does not hold: repair can be attempted (preconditions met) but not applied (no candidate token found, or repair produced no textual change).

4. **Raw vs final citation divergence:** `raw_answer_all_cited` and `all_answers_cited` (= `citation_quality["all_cited"]`) can and do differ: repair can fix a `raw_answer_all_cited=False` answer so that `all_answers_cited=True`, or leave it uncited.

5. **Fallback does not change `all_answers_cited`:** `citation_fallback_applied=True` means a prefix was prepended to `answer` for display, but `all_answers_cited` reflects citation completeness of the repaired answer text itself — not of the prefixed display string.

6. **`evidence_level` alignment with warnings:** If `citation_warnings` is non-empty, `evidence_level` is always `"degraded"` (never `"full"`).  `"full"` requires both `all_cited=True` and an empty `citation_warnings` list.

7. **Warning propagation:** Every warning added to `citation_warnings` is also appended to `warnings`.  The reverse is not true: `warnings` may contain operational warnings not present in `citation_warnings`.

8. **`citation_quality` mirrors top-level fields:** `citation_quality["all_cited"]` always equals the top-level `all_answers_cited`.  `citation_quality["raw_answer_all_cited"]` always equals the top-level `raw_answer_all_cited`.  `citation_quality["evidence_level"]` always equals the top-level fields used to derive `evidence_level`.

9. **`malformed_diagnostics_count` non-negative integer:** `malformed_diagnostics_count` is always present and is always a non-negative integer.  It equals zero when all retrieved hits have well-formed or absent diagnostics.  Absent/`None` diagnostics are not counted — only hits whose diagnostics are structurally invalid (root not a `dict`, or sub-field type errors) are counted.

---

## 4) Scenario Examples

### 4.1 Full citation — no repair, no fallback

The LLM produced a fully cited answer from the start.

```json
{
  "answer": "Claim A. [CITATION|chunk_id=abc|…]",
  "raw_answer": "Claim A. [CITATION|chunk_id=abc|…]",
  "raw_answer_all_cited": true,
  "all_answers_cited": true,
  "citation_repair_attempted": false,
  "citation_repair_applied": false,
  "citation_repair_strategy": null,
  "citation_repair_source_chunk_id": null,
  "citation_fallback_applied": false,
  "citation_quality": {
    "all_cited": true,
    "raw_answer_all_cited": true,
    "evidence_level": "full",
    "warning_count": 0,
    "citation_warnings": []
  },
  "warnings": []
}
```

### 4.2 Degraded citation — fallback applied

The LLM omitted citation tokens and repair did not run (run-scoped mode).

```json
{
  "answer": "Insufficient citations detected: Claim A without citation.",
  "raw_answer": "Claim A without citation.",
  "raw_answer_all_cited": false,
  "all_answers_cited": false,
  "citation_repair_attempted": false,
  "citation_repair_applied": false,
  "citation_repair_strategy": null,
  "citation_repair_source_chunk_id": null,
  "citation_fallback_applied": true,
  "citation_quality": {
    "all_cited": false,
    "raw_answer_all_cited": false,
    "evidence_level": "degraded",
    "warning_count": 1,
    "citation_warnings": ["Not all answer sentences or bullets end with a citation token."]
  },
  "warnings": ["Not all answer sentences or bullets end with a citation token."]
}
```

### 4.3 Repair applied — citation fixed, no fallback

All-runs mode (`all_runs=True`): the LLM omitted a citation token, repair appended the first retrieved token, and the answer became fully cited.

```json
{
  "answer": "Claim A. [CITATION|chunk_id=xyz|…]",
  "raw_answer": "Claim A.",
  "raw_answer_all_cited": false,
  "all_answers_cited": true,
  "citation_repair_attempted": true,
  "citation_repair_applied": true,
  "citation_repair_strategy": "append_first_retrieved_token",
  "citation_repair_source_chunk_id": "xyz",
  "citation_fallback_applied": false,
  "citation_quality": {
    "all_cited": true,
    "raw_answer_all_cited": false,
    "evidence_level": "full",
    "warning_count": 0,
    "citation_warnings": []
  },
  "warnings": []
}
```

Note: `raw_answer_all_cited` is `false` but `all_answers_cited` is `true` because repair fixed the missing citation.  `evidence_level` is `"full"` because the final delivered answer is fully cited and there are no citation warnings.

### 4.4 Repair applied but answer still degraded

All-runs mode: repair ran (and the answer text changed), but the repaired answer still has uncited segments.

```json
{
  "answer": "Insufficient citations detected: Claim A. Claim B. [CITATION|chunk_id=xyz|…]",
  "raw_answer": "Claim A. Claim B.",
  "raw_answer_all_cited": false,
  "all_answers_cited": false,
  "citation_repair_attempted": true,
  "citation_repair_applied": true,
  "citation_repair_strategy": "append_first_retrieved_token",
  "citation_repair_source_chunk_id": "xyz",
  "citation_fallback_applied": true,
  "citation_quality": {
    "all_cited": false,
    "raw_answer_all_cited": false,
    "evidence_level": "degraded",
    "warning_count": 1,
    "citation_warnings": ["Not all answer sentences or bullets end with a citation token."]
  },
  "warnings": ["Not all answer sentences or bullets end with a citation token."]
}
```

`citation_repair_applied` is `true` because the text changed; `citation_fallback_applied` is also `true` because the repaired text is still not fully cited.

### 4.5 No answer generated

The LLM returned an empty string (e.g. the question was out of scope or retrieval produced no hits).

```json
{
  "answer": "",
  "raw_answer": "",
  "raw_answer_all_cited": false,
  "all_answers_cited": false,
  "citation_repair_attempted": false,
  "citation_repair_applied": false,
  "citation_repair_strategy": null,
  "citation_repair_source_chunk_id": null,
  "citation_fallback_applied": false,
  "citation_quality": {
    "all_cited": false,
    "raw_answer_all_cited": false,
    "evidence_level": "no_answer",
    "warning_count": 0,
    "citation_warnings": []
  },
  "warnings": []
}
```

`evidence_level` is `"no_answer"` because the answer text is empty.  No warnings are raised for an empty answer (the LLM's refusal or silence is not a citation error).

### 4.6 Empty chunk text — degraded evidence with retrieval-time warning

A retrieved chunk had empty text during retrieval, raising an operational warning before postprocessing.

```json
{
  "answer": "Claim A. [CITATION|chunk_id=abc|…]",
  "raw_answer": "Claim A. [CITATION|chunk_id=abc|…]",
  "raw_answer_all_cited": true,
  "all_answers_cited": true,
  "citation_repair_attempted": false,
  "citation_repair_applied": false,
  "citation_repair_strategy": null,
  "citation_repair_source_chunk_id": null,
  "citation_fallback_applied": false,
  "citation_quality": {
    "all_cited": true,
    "raw_answer_all_cited": true,
    "evidence_level": "degraded",
    "warning_count": 1,
    "citation_warnings": ["Chunk 'abc' has empty or whitespace-only text."]
  },
  "warnings": ["Chunk 'abc' has empty or whitespace-only text."]
}
```

Even though the answer is fully cited, `evidence_level` is `"degraded"` because a citation-quality warning exists.  This reflects the fact that the cited chunk carried no usable text evidence.

### 4.7 Repair attempted but not applied — no candidate token found

All-runs mode (`all_runs=True`): repair preconditions were met (uncited answer, hits provided) but none of the retrieved hits contained a usable citation token.

```json
{
  "answer": "Insufficient citations detected: Claim A without citation.",
  "raw_answer": "Claim A without citation.",
  "raw_answer_all_cited": false,
  "all_answers_cited": false,
  "citation_repair_attempted": true,
  "citation_repair_applied": false,
  "citation_repair_strategy": null,
  "citation_repair_source_chunk_id": null,
  "citation_fallback_applied": true,
  "citation_quality": {
    "all_cited": false,
    "raw_answer_all_cited": false,
    "evidence_level": "degraded",
    "warning_count": 1,
    "citation_warnings": ["Not all answer sentences or bullets end with a citation token."]
  },
  "warnings": ["Not all answer sentences or bullets end with a citation token."]
}
```

`citation_repair_attempted` is `true` because repair logic was entered (all-runs mode, hits present, uncited answer).  `citation_repair_applied` is `false` because no citation token was available in the hits to append, so the answer text was unchanged.  Downstream consumers can use `citation_repair_attempted=true` + `citation_repair_applied=false` to distinguish this "attempted but unable to repair" case from the §4.2 case where repair was never entered at all.

---

## 5) Early-Return Result Contracts

`run_retrieval_and_qa()` has two short-circuit paths that return before `_postprocess_answer` runs.  These are called **early-return** paths.  Their result shapes differ from the live postprocessed shape documented in §2–§4 in predictable, contractual ways.

### 5.1 Dry-run (`status="dry_run"`)

When `config.dry_run=True`, the function returns immediately after the shared base dict is constructed.  No retrieval, embedder, or LLM call is made.

**Result shape invariants:**

| Field | Value |
|---|---|
| `status` | `"dry_run"` |
| `retrievers` | `["VectorCypherRetriever"]` (base); `+ ["graph expansion"]` when `expand_graph=True`; `+ ["graph expansion", "cluster traversal"]` when `cluster_aware=True` |
| `qa` | `"GraphRAG all-runs citations"` when `all_runs=True`; `"GraphRAG run-scoped citations"` otherwise |
| `answer` | `""` (default — no LLM ran) |
| `raw_answer` | `""` (default) |
| `all_answers_cited` | `False` (default) |
| `citation_quality.evidence_level` | `"no_answer"` (default — no answer was produced) |
| `citation_quality.all_cited` | `False` (default) |
| `citation_quality.warning_count` | `0` (default) |
| `citation_quality.citation_warnings` | `[]` (default) |
| `retrieval_path_summary` | `""` (default — no retrieval ran) |
| `malformed_diagnostics_count` | `0` (default — no hits were retrieved) |

**Fields absent from the dry-run result** (present only in live/postprocessed results):

- `hits` — no retrieval ran; the count is not applicable.
- `retrieval_results` — no retrieval ran; the list is not applicable.
- `warnings` — no operational warnings are raised during dry-run; the key is absent.
- `retrieval_skipped` — the retrieval-skipped sentinel is only set on the no-question path (§5.2).

**Example:**

```json
{
  "status": "dry_run",
  "retrievers": ["VectorCypherRetriever"],
  "qa": "GraphRAG run-scoped citations",
  "answer": "",
  "raw_answer": "",
  "all_answers_cited": false,
  "citation_repair_attempted": false,
  "citation_repair_applied": false,
  "citation_repair_strategy": null,
  "citation_repair_source_chunk_id": null,
  "citation_fallback_applied": false,
  "citation_quality": {
    "all_cited": false,
    "raw_answer_all_cited": false,
    "evidence_level": "no_answer",
    "warning_count": 0,
    "citation_warnings": []
  },
  "retrieval_path_summary": "",
  "malformed_diagnostics_count": 0
}
```

### 5.2 Retrieval skipped — no question provided (`status="live"`, `retrieval_skipped=True`)

When `question=None` in live mode (i.e. `config.dry_run=False`), the function short-circuits after validating the retrieval query but before opening a Neo4j driver or making any LLM call.

**Result shape invariants:**

| Field | Value |
|---|---|
| `status` | `"live"` |
| `retrieval_skipped` | `True` |
| `retrievers` | `[]` (nothing ran) |
| `hits` | `0` |
| `retrieval_results` | `[]` |
| `warnings` | `["No question provided; skipping vector retrieval."]` (exactly one entry) |
| `answer` | `""` (default — no LLM ran) |
| `raw_answer` | `""` (default) |
| `all_answers_cited` | `False` (default) |
| `citation_quality.evidence_level` | `"no_answer"` (default) |
| `citation_quality.citation_warnings` | `[]` (no citation-quality issues) |
| `retrieval_path_summary` | `""` (default — no retrieval ran) |
| `malformed_diagnostics_count` | `0` (default) |

The `warnings` list contains **exactly** the no-question skip message.  No citation-quality warnings are raised because no answer was produced.  The `citation_quality["citation_warnings"]` list is therefore empty, and the skip warning is **not** propagated to `citation_quality["citation_warnings"]` (it is an operational warning, not a citation-quality issue — consistent with §2.5.2).

**Example:**

```json
{
  "status": "live",
  "retrieval_skipped": true,
  "retrievers": [],
  "hits": 0,
  "retrieval_results": [],
  "warnings": ["No question provided; skipping vector retrieval."],
  "answer": "",
  "raw_answer": "",
  "all_answers_cited": false,
  "citation_repair_attempted": false,
  "citation_repair_applied": false,
  "citation_repair_strategy": null,
  "citation_repair_source_chunk_id": null,
  "citation_fallback_applied": false,
  "citation_quality": {
    "all_cited": false,
    "raw_answer_all_cited": false,
    "evidence_level": "no_answer",
    "warning_count": 0,
    "citation_warnings": []
  },
  "retrieval_path_summary": "",
  "malformed_diagnostics_count": 0
}
```

### 5.3 Distinguishing live from non-live results

| Field | `dry_run` | `retrieval_skipped` | Live postprocessed |
|---|---|---|---|
| `status` | `"dry_run"` | `"live"` | `"live"` |
| `retrieval_skipped` | *absent* | `True` | *absent* |
| `hits` | *absent* | `0` | `≥ 0` (integer) |
| `retrieval_results` | *absent* | `[]` | list of result dicts |
| `warnings` | *absent* | non-empty list | list (may be empty) |
| `answer` | `""` | `""` | LLM-generated string |
| `citation_quality.evidence_level` | `"no_answer"` | `"no_answer"` | `"no_answer"` / `"full"` / `"degraded"` |

Callers can reliably distinguish the three shapes:
- `result["status"] == "dry_run"` → dry-run early return (§5.1).
- `result.get("retrieval_skipped") is True` → no-question early return (§5.2).
- Otherwise → live postprocessed result (§2–§4).

---

## 6) Postprocessing Lifecycle

The full lifecycle executed by `_postprocess_answer` in order:

1. **Preserve `raw_answer`** — capture the original LLM output before any modification.
2. **Compute `raw_answer_all_cited`** — check whether every segment of `raw_answer` ends with a `[CITATION|…]` token.
3. **Attempt citation repair** (`_apply_citation_repair`) — in all-runs mode only, if `raw_answer_all_cited` is `False` and retrieved hits are available, attempt to append the first retrieved citation token.
4. **Apply citation fallback** (`_build_citation_fallback`) — if the repaired answer is still not fully cited, prepend the `"Insufficient citations detected: …"` prefix to the display answer and store only the bare prefix in the history answer.
5. **Derive `all_cited`** — check citation completeness of the repaired answer (independent of the fallback prefix).
6. **Collect `citation_warnings`** — merge any pre-postprocessing (retrieval-time) citation warnings (e.g. empty-chunk-text warnings) with any new warnings (e.g. uncited-answer warning).
7. **Derive `evidence_level`** — from `all_cited` and `citation_warnings` (see §2.8).
8. **Build `citation_quality` bundle** — structured dict consolidating citation state for callers.

---

## 7) Related Documents

- [Retrieval semantics v0.1](retrieval-semantics-v0.1.md) — chunk-first retrieval design, graph expansion layers, and citation-anchoring invariants
- [Claim argument model v0.3](claim-argument-model-v0.3.md) — `HAS_PARTICIPANT {role}` edge model underpinning participation-aware retrieval
- [Unstructured-first entity resolution v0.1](unstructured-first-entity-resolution-v0.1.md) — layered identity model for cluster and canonical enrichments

---

## Closing Note

This document is the canonical reference for postprocessing/result-field semantics in Power Atlas retrieval.  Any change to the meaning or population rules of the fields listed in §2 requires an explicit update to this document.
