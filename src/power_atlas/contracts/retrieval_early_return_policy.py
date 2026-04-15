"""Centralized early-return and short-circuit precedence rules for retrieval."""

from __future__ import annotations

from dataclasses import dataclass
from types import MappingProxyType
from typing import Mapping

__all__ = [
    "EarlyReturnRule",
    "EARLY_RETURN_PRECEDENCE",
    "EARLY_RETURN_RULE_BY_NAME",
    "resolve_early_return_rule",
]


@dataclass(frozen=True)
class EarlyReturnRule:
    priority: int
    name: str
    condition_description: str
    outcome_status: str
    absent_keys: frozenset[str]
    exclusive_keys: frozenset[str]
    wins_over: frozenset[str]
    section_ref: str

    def __post_init__(self) -> None:
        for field_name in ("absent_keys", "exclusive_keys", "wins_over"):
            object.__setattr__(self, field_name, frozenset(getattr(self, field_name)))


EARLY_RETURN_PRECEDENCE: tuple[EarlyReturnRule, ...] = (
    EarlyReturnRule(
        priority=1,
        name="dry_run",
        condition_description=(
            "config.dry_run=True — evaluated before any question or retrieval "
            "guards. No retrieval, embedder, or LLM call is made. Result carries "
            "status='dry_run'; the keys hits, retrieval_results, warnings, and "
            "retrieval_skipped are absent."
        ),
        outcome_status="dry_run",
        absent_keys=frozenset({"hits", "retrieval_results", "warnings", "retrieval_skipped"}),
        exclusive_keys=frozenset(),
        wins_over=frozenset({"retrieval_skipped"}),
        section_ref="§5.1",
    ),
    EarlyReturnRule(
        priority=2,
        name="retrieval_skipped",
        condition_description=(
            "question=None in live mode (config.dry_run=False) — evaluated after "
            "dry_run. Short-circuits before any Neo4j driver or LLM call. Result "
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

priorities = sorted(rule.priority for rule in EARLY_RETURN_PRECEDENCE)
if priorities != list(range(1, len(EARLY_RETURN_PRECEDENCE) + 1)):
    raise ValueError(
        "EARLY_RETURN_PRECEDENCE priorities must be unique integers starting at 1; "
        f"got {priorities!r}"
    )

known_names = frozenset(rule.name for rule in EARLY_RETURN_PRECEDENCE)
for rule in EARLY_RETURN_PRECEDENCE:
    unresolved = rule.wins_over - known_names
    if unresolved:
        raise ValueError(
            f"Rule {rule.name!r} wins_over references unknown rule name(s): {unresolved!r}"
        )
    if rule.name in rule.wins_over:
        raise ValueError(f"Rule {rule.name!r} must not list itself in wins_over")

names = [rule.name for rule in EARLY_RETURN_PRECEDENCE]
if len(names) != len(set(names)):
    duplicates = {name for name in names if names.count(name) > 1}
    raise ValueError(
        "EARLY_RETURN_PRECEDENCE rule names must be unique; "
        f"duplicate name(s): {duplicates!r}"
    )

EARLY_RETURN_RULE_BY_NAME: Mapping[str, EarlyReturnRule] = MappingProxyType(
    {rule.name: rule for rule in EARLY_RETURN_PRECEDENCE}
)


def resolve_early_return_rule(
    *,
    is_dry_run: bool,
    question: str | None,
) -> EarlyReturnRule | None:
    conditions: dict[str, bool] = {
        "dry_run": is_dry_run,
        "retrieval_skipped": question is None,
    }
    unknown = {rule.name for rule in EARLY_RETURN_PRECEDENCE} - conditions.keys()
    if unknown:
        raise RuntimeError(
            f"resolve_early_return_rule: no condition defined for rule(s) {unknown!r}; "
            "add the missing condition(s) to the conditions dict in this function."
        )
    for rule in EARLY_RETURN_PRECEDENCE:
        if conditions[rule.name]:
            return rule
    return None