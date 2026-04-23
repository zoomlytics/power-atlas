from __future__ import annotations

from pathlib import Path
from typing import Any, Callable


def lint_and_clean_structured_csvs_legacy(
    run_id: str,
    output_dir: Path,
    *,
    resolve_dataset_root: Callable[..., object],
    lint_and_clean_structured_csvs: Callable[..., dict[str, Any]],
) -> dict[str, Any]:
    dataset_root = resolve_dataset_root()
    return lint_and_clean_structured_csvs(
        run_id=run_id,
        output_dir=output_dir,
        fixtures_dir=dataset_root.root,
        dataset_id=dataset_root.dataset_id,
    )

__all__ = [
    "lint_and_clean_structured_csvs_legacy",
]