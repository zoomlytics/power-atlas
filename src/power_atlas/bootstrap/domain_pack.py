from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class DomainPackDescriptor:
    name: str
    version: str
    provides: tuple[str, ...] = ()
    examples: tuple[str, ...] = ()


__all__ = ["DomainPackDescriptor"]