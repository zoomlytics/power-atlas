from __future__ import annotations

import json
from collections.abc import Callable
from typing import Any


def run_narrative_extraction_main(
    *,
    parse_args: Callable[[], Any],
    run_narrative_extraction: Callable[[Any], dict[str, Any]],
    emit: Callable[[str], None] = print,
) -> None:
    config = parse_args()
    summary = run_narrative_extraction(config)
    emit(json.dumps(summary, indent=2))


__all__ = ["run_narrative_extraction_main"]