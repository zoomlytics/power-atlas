"""Centralized early-return and short-circuit precedence rules for retrieval.

This module is the single canonical in-code reference for the ordered set of
conditions that cause ``run_retrieval_and_qa()`` to return before reaching the
live retrieval / postprocessing path.

Background
----------
``run_retrieval_and_qa()`` has two early-return (non-live) paths — documented in
§5 of ``docs/architecture/retrieval-citation-result-contract-v0.1.md``.  Before
this module existed, the ordering rules for these paths were encoded implicitly in
control flow and existed only in test docstrings and prose documentation.  When
multiple conditions are simultaneously true (e.g. ``dry_run=True`` **and**
``question=None``), contributors had no in-code reference to determine which
result shape the function returns.

This module provides:

1. :class:`EarlyReturnRule` — a frozen dataclass describing one entry in the
   precedence table.
2. :data:`EARLY_RETURN_PRECEDENCE` — an immutable, ordered tuple of all current
   early-return rules listed from *highest to lowest* priority.  The first rule
   whose condition is satisfied wins; later rules are not evaluated.

Precedence table summary
------------------------
+----------+--------------------+-----------------------------------+-------------------+-----------------------+
| Priority | Name               | Trigger condition                 | outcome_status    | Wins over             |
+==========+====================+===================================+===================+=======================+
| 1        | dry_run            | ``config.dry_run=True``           | ``"dry_run"``     | ``retrieval_skipped`` |
+----------+--------------------+-----------------------------------+-------------------+-----------------------+
| 2        | retrieval_skipped  | ``question is None`` (live mode)  | ``"live"``        | —                     |
+----------+--------------------+-----------------------------------+-------------------+-----------------------+

Key rules encoded here
----------------------
- **dry_run beats retrieval_skipped**: when ``config.dry_run=True`` *and*
  ``question=None`` the result carries ``status="dry_run"`` — the dry_run guard
  runs first and the function returns before the ``question is None`` guard is
  reached.
- **dry_run beats question=""**: an empty-string question does not trigger the
  retrieval-skipped path; ``dry_run=True`` still returns the dry-run result.
- **dry_run beats retrieval-mode modifiers** (``all_runs``, ``expand_graph``,
  ``cluster_aware``): passing these alongside ``dry_run=True`` does not inject
  live-only keys (``hits``, ``retrieval_results``, ``warnings``,
  ``retrieval_skipped``) into the result.
- **question="" is not a retrieval-skipping sentinel**: only ``question=None``
  activates the ``retrieval_skipped`` path; an empty string passes through to
  live retrieval.

Machine-readable complement
----------------------------
This module is the *machine-readable* complement to §5 of the contract document —
not a replacement for it.  The full result-shape invariants for each rule (exact
key sets, field values, ``debug_view`` defaults, etc.) remain in the contract
document.

Contract doc cross-reference
-----------------------------
§5.1 (dry_run)            — ``EarlyReturnRule.name == "dry_run"``
§5.2 (retrieval_skipped)  — ``EarlyReturnRule.name == "retrieval_skipped"``
§5.3 (caller distinction) — ``EarlyReturnRule.outcome_status`` + ``exclusive_keys``
"""

from __future__ import annotations

from dataclasses import dataclass
from types import MappingProxyType

__all__ = [
    "EarlyReturnRule",
    "EARLY_RETURN_PRECEDENCE",
    "EARLY_RETURN_RULE_BY_NAME",
]

# ---------------------------------------------------------------------------
# Rule dataclass
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class EarlyReturnRule:
    """One ordered entry in the early-return / short-circuit precedence table.

    Instances are immutable (``frozen=True``).  All collection fields are
    :class:`frozenset` so they cannot be mutated after construction.

    Attributes
    ----------
    priority:
        Evaluation order — **lower value = higher priority**.  The runtime
        evaluates rules in ascending priority order; the first matching condition
        wins and ``run_retrieval_and_qa()`` returns immediately.
    name:
        Short, stable identifier for this rule.  Used in ``wins_over`` references
        and in test assertions.  Examples: ``"dry_run"``, ``"retrieval_skipped"``.
    condition_description:
        Human-readable description of the trigger condition, suitable for
        docstrings, error messages, and debugging.
    outcome_status:
        Value of the ``"status"`` key in the result dict when this rule fires.
    absent_keys:
        Top-level result keys that are **absent** (not present at all) when this
        rule fires.  Complement of the required-key set relative to the live result.
    exclusive_keys:
        Top-level result keys that are **exclusive** to this rule's result shape —
        present only when this rule fires, absent on all other paths.
    wins_over:
        Names of rules that this rule *preempts* when both conditions are
        simultaneously true.  If ``"retrieval_skipped"`` appears here, it means
        this rule's check runs first and the caller receives this rule's result
        shape rather than the ``retrieval_skipped`` shape.
    section_ref:
        Reference to the section in the canonical contract document that describes
        the full result-shape invariants for this rule (e.g. ``"§5.1"``).
    """

    priority: int
    name: str
    condition_description: str
    outcome_status: str
    absent_keys: frozenset[str]
    exclusive_keys: frozenset[str]
    wins_over: frozenset[str]
    section_ref: str


# ---------------------------------------------------------------------------
# Precedence table
# ---------------------------------------------------------------------------

#: Ordered tuple of all current early-return rules for ``run_retrieval_and_qa()``.
#:
#: Rules are listed from **highest to lowest priority** (``priority=1`` first).
#: The runtime evaluates conditions from index 0 upward; the first match wins.
#:
#: This tuple is the machine-readable complement to §5 of the contract document:
#: ``docs/architecture/retrieval-citation-result-contract-v0.1.md``
#:
#: To look up a rule by name use the module-level helper
#: ``{rule.name: rule for rule in EARLY_RETURN_PRECEDENCE}``.
EARLY_RETURN_PRECEDENCE: tuple[EarlyReturnRule, ...] = (
    # -----------------------------------------------------------------------
    # Priority 1 — dry_run (§5.1)
    # -----------------------------------------------------------------------
    EarlyReturnRule(
        priority=1,
        name="dry_run",
        condition_description=(
            "config.dry_run=True — evaluated before any question or retrieval "
            "guards.  No retrieval, embedder, or LLM call is made.  Result carries "
            "status='dry_run'; the keys hits, retrieval_results, warnings, and "
            "retrieval_skipped are absent."
        ),
        outcome_status="dry_run",
        absent_keys=frozenset({"hits", "retrieval_results", "warnings", "retrieval_skipped"}),
        exclusive_keys=frozenset(),
        wins_over=frozenset({"retrieval_skipped"}),
        section_ref="§5.1",
    ),
    # -----------------------------------------------------------------------
    # Priority 2 — retrieval_skipped (§5.2)
    # -----------------------------------------------------------------------
    EarlyReturnRule(
        priority=2,
        name="retrieval_skipped",
        condition_description=(
            "question=None in live mode (config.dry_run=False) — evaluated after "
            "dry_run.  Short-circuits before any Neo4j driver or LLM call.  Result "
            "carries status='live', retrieval_skipped=True, hits=0, "
            "retrieval_results=[], and a skip warning in warnings."
        ),
        outcome_status="live",
        absent_keys=frozenset(),
        exclusive_keys=frozenset({"retrieval_skipped"}),
        wins_over=frozenset(),
        section_ref="§5.2",
    ),
)

# ---------------------------------------------------------------------------
# Integrity checks (import-time)
# ---------------------------------------------------------------------------

# Ensure priorities are unique and form a dense sequence starting at 1.
_priorities = sorted(r.priority for r in EARLY_RETURN_PRECEDENCE)
assert _priorities == list(range(1, len(EARLY_RETURN_PRECEDENCE) + 1)), (
    "EARLY_RETURN_PRECEDENCE priorities must be unique integers starting at 1; "
    f"got {_priorities!r}"
)

# Ensure all wins_over references resolve to known rule names.
_known_names = frozenset(r.name for r in EARLY_RETURN_PRECEDENCE)
for _rule in EARLY_RETURN_PRECEDENCE:
    _unresolved = _rule.wins_over - _known_names
    assert not _unresolved, (
        f"Rule {_rule.name!r} wins_over references unknown rule name(s): {_unresolved!r}"
    )

# Ensure no rule lists itself in wins_over.
for _rule in EARLY_RETURN_PRECEDENCE:
    assert _rule.name not in _rule.wins_over, (
        f"Rule {_rule.name!r} must not list itself in wins_over"
    )

# Expose a convenience lookup (name → rule) as a read-only mapping.
#: Read-only mapping from rule name to :class:`EarlyReturnRule`.
#: Convenience alias; do not mutate.
EARLY_RETURN_RULE_BY_NAME: MappingProxyType[str, EarlyReturnRule] = MappingProxyType(
    {rule.name: rule for rule in EARLY_RETURN_PRECEDENCE}
)
