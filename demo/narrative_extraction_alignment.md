## Narrative extraction vendor alignment checklist

- [x] Structured output + schema alignment (uses `claim_extraction_schema` and structured output extractor)
- [x] Extractor parameters follow vendor defaults (`use_structured_output=True`, `create_lexical_graph=False`)
- [x] Manifest contract aligned to shared stage manifest (`build_stage_manifest` + `write_manifest`)
- [x] Run scoping + identifier validation reused from `RunScopedNeo4jChunkReader`/shared lexical config
- [x] Provenance/evidence edges reuse shared writer + normalized warnings in summary

Notes:
- Narrative lexical graph config now reuses the contract-backed `claim_extraction_lexical_config` for chunk labels/properties sourced from the pipeline contract.
- Manifest entries now match the demo-wide stage manifest shape (run scopes, config block, and stage payload with summary path).
