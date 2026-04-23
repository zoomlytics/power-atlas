from __future__ import annotations

import importlib


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