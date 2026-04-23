from __future__ import annotations

import ast
import importlib
from pathlib import Path


REMOVED_STAGE_ADAPTERS = {
    "demo.stages.pdf_ingest": ["run_pdf_ingest"],
    "demo.stages.claim_extraction": ["run_claim_and_mention_extraction"],
    "demo.stages.entity_resolution": ["run_entity_resolution"],
    "demo.stages.retrieval_and_qa": ["run_retrieval_and_qa", "run_interactive_qa"],
    "demo.stages": [
        "run_pdf_ingest",
        "run_claim_and_mention_extraction",
        "run_entity_resolution",
        "run_retrieval_and_qa",
        "run_interactive_qa",
    ],
}


def test_removed_stage_adapters_are_no_longer_exported() -> None:
    for module_name, adapter_names in REMOVED_STAGE_ADAPTERS.items():
        module = importlib.import_module(module_name)
        for adapter_name in adapter_names:
            assert not hasattr(module, adapter_name), (
                f"{module_name}.{adapter_name} should be deleted once the RequestContext "
                "entrypoint owns the stage boundary."
            )


def test_repo_does_not_use_demo_stages_proxy_imports() -> None:
    repo_root = Path(__file__).resolve().parents[2]
    offenders: list[str] = []

    for path in sorted(repo_root.rglob("*.py")):
        if any(part in {".venv", "vendor", "vendor-resources", "__pycache__"} for part in path.parts):
            continue

        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        rel_path = path.relative_to(repo_root)
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module == "demo.stages":
                offenders.append(f"{rel_path}:{node.lineno}")
            if isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.name == "demo.stages":
                        offenders.append(f"{rel_path}:{node.lineno}")

    assert not offenders, (
        "Import concrete stage modules directly instead of using the removed demo.stages "
        f"proxy surface: {offenders}"
    )