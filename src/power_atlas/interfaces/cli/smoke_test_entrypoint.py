from __future__ import annotations

import tempfile
from collections.abc import Callable
from contextlib import ExitStack
from pathlib import Path
from typing import Any


def run_smoke_test_main(
    *,
    parse_args: Callable[[], Any],
    run_structured_scenario: Callable[[Path], Path],
    run_unstructured_scenario: Callable[[Path], Path],
    run_batch_scenario: Callable[[Path], Path],
    emit: Callable[[str], None] = print,
) -> None:
    args = parse_args()
    with ExitStack() as stack:
        output_dir = args.output_dir or Path(
            stack.enter_context(tempfile.TemporaryDirectory(prefix="smoke_"))
        )
        structured_path = run_structured_scenario(output_dir)
        emit(f"[PASS] structured-only: {structured_path}")
        unstructured_path = run_unstructured_scenario(output_dir)
        emit(f"[PASS] unstructured-only: {unstructured_path}")
        batch_path = run_batch_scenario(output_dir)
        emit(f"[PASS] batch: {batch_path}")
        emit("Smoke test passed.")


__all__ = ["run_smoke_test_main"]