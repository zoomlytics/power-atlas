# power-atlas Makefile
#
# Phase 1 safety harness targets.
# See docs/repository_restructure/repository_restructure_phase1_execution_run_log.md

.PHONY: phase1-verify installed-package-adoption installed-package-adoption-only

## installed-package-adoption: Run the installed-package adoption proof set.
##
## Covers:
##   - package import and facade smoke checks
##   - installed console-script contract checks
##   - outside-repo copied-script adoption proofs for consumer/starter examples
##   - outside-repo copied-script adoption proofs for backend example apps
##
## Prerequisites:
##   - .venv activated or present at .venv/
##   - editable install completed: python -m pip install -e ".[dev]"
installed-package-adoption:
	python -m pytest tests/test_power_atlas_package.py tests/test_installed_package_adoption.py

## installed-package-adoption-only: Run only the dedicated installed-package adoption module.
##
## Use this when you want the narrowest outside-repo/adoption proof without the
## companion package smoke module.
installed-package-adoption-only:
	python -m pytest tests/test_installed_package_adoption.py

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
