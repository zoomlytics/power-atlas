# Warning-Channel Conventions

This document defines the canonical warning-handling policy for Power Atlas.
All new code should follow these conventions. Deviations require an explicit
comment explaining the exception.

---

## Overview

Four warning mechanisms exist in the codebase.  They are **not interchangeable**;
each serves a distinct audience and delivery path:

| Mechanism | Audience | Delivery path | Persistence |
|-----------|----------|---------------|-------------|
| `_logger.warning(...)` | Operators / log aggregators | Python `logging` hierarchy | Captured by any `logging` handler |
| `result["warnings"]` list | Callers / orchestrators | Return value of a stage or pipeline function | Carried in the data payload |
| `print(...)` to stdout | Interactive CLI users | Terminal stdout | Ephemeral (terminal session) |
| `warnings.warn(...)` | **Not used** — see [below](#warningswarn) | Python warnings machinery | Filtered by `warnings` module |

---

## 1 — `_logger.warning(...)`

**Use this for all runtime operational warnings.**

Operational warnings are conditions that are abnormal but non-fatal: the
system can continue, but an operator should be aware.  Examples include
unexpected data shapes, fallback-to-default paths, and resource-state
mismatches that are recovered automatically.

```python
# demo/contracts/pipeline.py
_logger.warning(
    "Falling back to default chunk embedding contract; unable to load %s: %s",
    PDF_PIPELINE_CONFIG_PATH,
    exc,
)

# demo/stages/retrieval_and_qa.py
_logger.warning("Chunk %s has empty or whitespace-only text", chunk_id)
```

**Rules:**
- Create the logger at module level with `_logger = logging.getLogger(__name__)`.
- Use `%`-style format strings (not f-strings) so the message is not
  formatted until a handler actually needs it.
- Do **not** use `warnings.warn(...)` as a substitute for this channel.

---

## 2 — Returned `warnings` lists in stage results

**Use this for warnings that callers or orchestrators must surface.**

Stage runner functions (e.g. `run_graph_health_diagnostics`,
`run_retrieval_benchmark`) return a dict.  When a condition warrants a
human-visible notice alongside the structured result, append a plain-English
message to a `warnings` key in that dict.  The **caller** (typically a CLI
`main()`) is responsible for routing each entry through `_logger.warning`.

```python
# Stage function (demo/stages/graph_health.py)
collected_warnings: list[str] = []
if not nodes_found:
    collected_warnings.append("No demo-owned nodes found; graph may be empty.")
return {"status": "live", ..., "warnings": collected_warnings}

# CLI entry point (pipelines/query/graph_health_diagnostics.py)
for msg in result.get("warnings", []):
    _logger.warning(msg)
```

**Rules:**
- The `warnings` key must always be present in a result dict (empty list, not
  absent) so callers can iterate without a `KeyError` guard.
- Entries must be plain strings — no exception objects, no markup.
- The CLI layer must not print these warnings directly; it must route them
  through `_logger.warning` so they appear in the log stream.

---

## 3 — CLI `print(...)` warnings to stdout

**Use this only for interactive, user-facing notices from CLI commands.**

Some CLI sub-commands are interactive utilities (e.g. the `reset` command in
`demo/run_demo.py`).  Warnings from these commands are directed to **stdout**
so they are clearly visible in the terminal and are easy to capture in scripts.
These warnings are intentionally outside the logging hierarchy because the
audience is a human at the terminal, not an operator reading aggregated logs.

```python
# demo/run_demo.py — reset sub-command
for warning in report.get("warnings", []):
    print(f"  warning: {warning}")
```

**Rules:**
- Use `print(...)` **only** in CLI command handlers, never in library or stage
  code.
- Direct output to **stdout** (the default) unless the message is a fatal
  error, in which case use `sys.stderr`.
- Prefix each line with a consistent token (e.g. `"  warning: "`) so scripts
  can grep reliably.

---

## 4 — `warnings.warn(...)`

**Not part of the intended long-term warning model. Do not introduce new uses.**

`warnings.warn(...)` is a Python library mechanism designed for deprecation
notices and inter-library API alerts.  It is not suitable for operational or
user-facing pipeline warnings because:

- It is silenced by default after the first occurrence (`once` filter).
- It is invisible to standard `logging` handlers and log aggregators.
- Its `stacklevel` behavior can be confusing inside module-level initialisation
  code.

All previously existing `warnings.warn(...)` calls in
`demo/contracts/pipeline.py` have been migrated to `_logger.warning(...)` so
that config-loading fallback conditions appear in the standard log stream.

**Rule:** Do not add new `warnings.warn(...)` calls.  The only acceptable
exception would be a public library API that explicitly follows the Python
deprecation-warning convention, and even then it must be documented as a
deliberate exception here.

---

## Summary decision table

| Situation | Use |
|-----------|-----|
| Config/YAML parse error or fallback at import time | `_logger.warning(...)` |
| Non-fatal anomaly inside a stage runner | `_logger.warning(...)` **and/or** append to `result["warnings"]` if callers need to surface it |
| Stage result carries a notice the CLI must relay | `result["warnings"]` list entry, routed via `_logger.warning` in the CLI layer |
| Interactive CLI command needs a human-visible notice | `print(f"  warning: {msg}")` to stdout |
| Public deprecation notice in a library API | `warnings.warn(..., DeprecationWarning)` — requires explicit doc comment |
