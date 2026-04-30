from __future__ import annotations

import argparse
from pathlib import Path


def parse_smoke_test_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run demo smoke test")
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=None,
        help="Optional manifest output directory; defaults to an isolated temporary directory.",
    )
    return parser.parse_args(argv)


__all__ = ["parse_smoke_test_args"]