from __future__ import annotations

import argparse


def parse_sync_vendor_version_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Sync vendor version metadata with the submodule gitlink SHA."
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="Fail if the version file is out of sync",
    )
    return parser.parse_args(argv)


__all__ = ["parse_sync_vendor_version_args"]