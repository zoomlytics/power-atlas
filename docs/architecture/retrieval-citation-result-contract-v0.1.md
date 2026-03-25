# Power Atlas — Retrieval/Citation Result Contract (v0.1)

**Status:** Accepted  
**Audience:** Contributors, architects, reviewers  
**Scope:** Postprocessing semantics for the retrieval/citation result dict returned by `run_retrieval_and_qa`

---

## 1) Summary

`run_retrieval_and_qa` returns a result dict that contains both the **final deliverable fields** (what callers and the UI consume) and **diagnostic fields** (what tests and observability tooling inspect).  The postprocessing path — citation repair, citation fallback, evidence-level derivation — runs through a single shared helper (`_postprocess_answer`) so the single-shot and interactive paths stay aligned.

This document is the canonical reference for the meaning, relationships, and invariants of every postprocessing/result field.  It is not a description of the retrieval architecture itself (see [retrieval-semantics-v0.1.md](retrieval-semantics-v0.1.md)); it focuses exclusively on what the result dict carries and why.

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
| `citation_repair_applied` | `bool` | `True` **only** when repair logic ran *and* the answer text actually changed as a result. |
| `citation_repair_strategy` | `str \| None` | Name of the repair algorithm used (e.g. `"append_first_retrieved_token"`), or `None` when `citation_repair_applied` is `False`. |
| `citation_repair_source_chunk_id` | `str \| None` | `chunk_id` of the retrieved chunk whose citation token was used during repair, or `None` when `citation_repair_applied` is `False`. |

**Repair invariants:**

- `citation_repair_applied` reflects whether the **answer text changed**, not merely whether repair logic was invoked.  If repair ran but produced a string identical to the input, `citation_repair_applied` is `False`.
- `citation_repair_strategy` and `citation_repair_source_chunk_id` are **only populated when `citation_repair_applied` is `True`**.  When `citation_repair_applied` is `False`, both are `None`.
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
| `evidence_level` | `"no_answer" \| "full" \| "degraded"` | Encodes overall citation quality (see §2.6). |
| `warning_count` | `int` | `len(citation_warnings)`. |
| `citation_warnings` | `list[str]` | All citation-quality warnings, including warnings that were raised before postprocessing (e.g. empty-chunk-text warnings). |

#### 2.5.2 `warnings` vs `citation_warnings`

`warnings` is the **top-level operational warnings list** returned in the result dict.  It is a superset:

- It contains every warning that was also added to `citation_warnings` (e.g. the uncited-answer warning, the empty-chunk-text warning).
- It may also contain additional operational warnings that are **not** citation-quality issues (e.g. the `"No question provided; skipping vector retrieval."` warning).

`citation_warnings` (inside `citation_quality`) contains **only citation-quality-related** warnings.  Callers that want to assess citation quality specifically should use `citation_quality["citation_warnings"]`; callers that want all warnings should use the top-level `warnings` list.

### 2.6 Evidence-level semantics

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

1. **Repair-applied invariant:** `citation_repair_strategy` and `citation_repair_source_chunk_id` are `None` whenever `citation_repair_applied` is `False`.  They are non-`None` only when `citation_repair_applied` is `True`.

2. **Text-change invariant:** `citation_repair_applied = True` means the repaired answer text *differs* from `raw_answer`.  If repair ran but produced identical text, `citation_repair_applied` remains `False`.

3. **Raw vs final citation divergence:** `raw_answer_all_cited` and `all_answers_cited` (= `citation_quality["all_cited"]`) can and do differ: repair can fix a `raw_answer_all_cited=False` answer so that `all_answers_cited=True`, or leave it uncited.

4. **Fallback does not change `all_answers_cited`:** `citation_fallback_applied=True` means a prefix was prepended to `answer` for display, but `all_answers_cited` reflects citation completeness of the repaired answer text itself — not of the prefixed display string.

5. **`evidence_level` alignment with warnings:** If `citation_warnings` is non-empty, `evidence_level` is always `"degraded"` (never `"full"`).  `"full"` requires both `all_cited=True` and an empty `citation_warnings` list.

6. **Warning propagation:** Every warning added to `citation_warnings` is also appended to `warnings`.  The reverse is not true: `warnings` may contain operational warnings not present in `citation_warnings`.

7. **`citation_quality` mirrors top-level fields:** `citation_quality["all_cited"]` always equals the top-level `all_answers_cited`.  `citation_quality["raw_answer_all_cited"]` always equals the top-level `raw_answer_all_cited`.  `citation_quality["evidence_level"]` always equals the top-level fields used to derive `evidence_level`.

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

### 4.6 Empty chunk text — degraded evidence with pre-retrieval warning

A retrieved chunk had empty text, raising an operational warning before postprocessing.

```json
{
  "answer": "Claim A. [CITATION|chunk_id=abc|…]",
  "raw_answer": "Claim A. [CITATION|chunk_id=abc|…]",
  "raw_answer_all_cited": true,
  "all_answers_cited": true,
  "citation_repair_applied": false,
  "citation_repair_strategy": null,
  "citation_repair_source_chunk_id": null,
  "citation_fallback_applied": false,
  "citation_quality": {
    "all_cited": true,
    "raw_answer_all_cited": true,
    "evidence_level": "degraded",
    "warning_count": 1,
    "citation_warnings": ["Retrieved chunk chunk_id=abc has empty text; evidence quality may be degraded."]
  },
  "warnings": ["Retrieved chunk chunk_id=abc has empty text; evidence quality may be degraded."]
}
```

Even though the answer is fully cited, `evidence_level` is `"degraded"` because a citation-quality warning exists.  This reflects the fact that the cited chunk carried no usable text evidence.

---

## 5) Postprocessing Lifecycle

The full lifecycle executed by `_postprocess_answer` in order:

1. **Preserve `raw_answer`** — capture the original LLM output before any modification.
2. **Compute `raw_answer_all_cited`** — check whether every segment of `raw_answer` ends with a `[CITATION|…]` token.
3. **Attempt citation repair** (`_apply_citation_repair`) — in all-runs mode only, if `raw_answer_all_cited` is `False` and retrieved hits are available, attempt to append the first retrieved citation token.
4. **Apply citation fallback** (`_build_citation_fallback`) — if the repaired answer is still not fully cited, prepend the `"Insufficient citations detected: …"` prefix to the display answer and store only the bare prefix in the history answer.
5. **Derive `all_cited`** — check citation completeness of the repaired answer (independent of the fallback prefix).
6. **Collect `citation_warnings`** — merge any pre-retrieval citation warnings (e.g. empty-chunk-text warnings) with any new warnings (e.g. uncited-answer warning).
7. **Derive `evidence_level`** — from `all_cited` and `citation_warnings` (see §2.6).
8. **Build `citation_quality` bundle** — structured dict consolidating citation state for callers.

---

## 6) Related Documents

- [Retrieval semantics v0.1](retrieval-semantics-v0.1.md) — chunk-first retrieval design, graph expansion layers, and citation-anchoring invariants
- [Claim argument model v0.3](claim-argument-model-v0.3.md) — `HAS_PARTICIPANT {role}` edge model underpinning participation-aware retrieval
- [Unstructured-first entity resolution v0.1](unstructured-first-entity-resolution-v0.1.md) — layered identity model for cluster and canonical enrichments

---

## Closing Note

This document is the canonical reference for postprocessing/result-field semantics in Power Atlas retrieval.  Any change to the meaning or population rules of the fields listed in §2 requires an explicit update to this document.
