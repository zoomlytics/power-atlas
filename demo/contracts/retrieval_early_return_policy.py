"""Compatibility shim for retrieval early-return policy."""

from power_atlas.contracts.retrieval_early_return_policy import (
    EARLY_RETURN_PRECEDENCE,
    EARLY_RETURN_RULE_BY_NAME,
    EarlyReturnRule,
    resolve_early_return_rule,
)

__all__ = [
    "EarlyReturnRule",
    "EARLY_RETURN_PRECEDENCE",
    "EARLY_RETURN_RULE_BY_NAME",
    "resolve_early_return_rule",
]
