# Wikidata Extraction Prompt Templates

`demo/fixtures/wikidata_extraction_prompts/` is an operator-facing prototyping
template subtree.

These files are retained for the human workflow used to construct and review
external Wikidata-backed fixture material. They are not part of the runtime
dataset-loading path for `python -m demo.run_demo ...`, and they are not a
current Phase 10 retirement target.

Current posture:

- keep this subtree defer-in-place while operators still use it during dataset
  prototyping,
- do not treat these markdown prompt templates as dead runtime compatibility
  debris simply because they are not code-called,
- reconsider retirement only if the external Wikidata dataset-construction
  workflow is intentionally replaced or removed.

Files in this directory:

- `graph_rag_wikidata_prompt_template_stage_1.md`
- `graph_rag_wikidata_prompt_template_stage_2.md`
- `graph_rag_wikidata_dataset_review_prompt.md`

See also:

- [`../README.md`](../README.md)
- `docs/repository_restructure/repository_restructure_decisions.md`
- `docs/repository_restructure/repository_restructure_phase10_legacy_retirement_shortlist.md`