# power-atlas Makefile
#
# Phase 1 safety harness targets.
# See docs/repository_restructure/repository_restructure_phase1_execution_run_log.md

.PHONY: phase1-verify

## phase1-verify: Run the Phase 1 safety harness verification (reset → baseline → companion isolation → artifact capture).
##
## Prerequisites:
##   - Neo4j running:    docker compose up -d neo4j
##   - .venv activated or present at .venv/
##   - OPENAI_API_KEY and NEO4J_PASSWORD set in environment
##   - OPENAI_MODEL unset or set to gpt-5.4
##
## Artifacts written to:
##   artifacts/repository_restructure/phase1/<timestamp>/
phase1-verify:
	bash scripts/phase1_verify.sh
