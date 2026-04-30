from __future__ import annotations

from collections.abc import Callable
from typing import Any


def run_sync_vendor_version_main(
    *,
    parse_args: Callable[[list[str] | None], Any],
    sync_version_file: Callable[..., int],
    argv: list[str] | None = None,
) -> int:
    args = parse_args(argv)
    return sync_version_file(check_only=args.check)


__all__ = ["run_sync_vendor_version_main"]