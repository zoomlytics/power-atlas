# Repository Restructure Safety Harness

Status: Accepted  
Applies to: `zoomlytics/power-atlas`  
Related documents:
- `docs/repository_restructure/repository_restructure_plan.md`
- `docs/repository_restructure/repository_restructure_decisions.md`
- `docs/repository_restructure/repository_restructure_checklist.md`

This document defines the minimum behavioral safety harness required before broad repository restructuring begins.

It is intended to:

- identify the critical product flows that must survive structural migration,
- define the initial golden-path scenarios used for before/after comparison,
- define at least one Neo4j-backed integration path that must remain functional,
- define package/import validation expectations,
- make “behavior preserved” concrete enough to support Phase 1 exit criteria.

It is **not** intended to be a full test plan or a comprehensive QA strategy.  
It is a migration control document for early restructure work.

---

## 1. Safety harness purpose

The repository restructure will move code, imports, package boundaries, and runtime assembly.  
Those changes are high-risk even when no product behavior is intentionally changed.

The purpose of this safety harness is to ensure that:

- structural changes do not silently break core product flows,
- the team has a small number of trustworthy checks before moving code,
- “behavior preserved” has an operational meaning,
- migration work is blocked if core functionality stops working.

This document governs **Phase 1 — Migration safety harness** in the canonical restructure plan.

---

## 2. Safety harness scope

The first-pass safety harness should stay intentionally small.

It must cover:

- one critical CLI path,
- one critical API path, if an API is currently part of the active product,
- one critical graph retrieval path,
- one critical answer/citation path,
- one critical ingestion or enrichment path, if it is currently part of the active product flow,
- at least one real Neo4j-backed integration path,
- package/import validation through the intended project installation path.

It does **not** need to cover:

- every edge case,
- every historical command or script,
- every evaluation workflow,
- every non-core or experimental path,
- unstable outputs that cannot provide a meaningful signal.

---

## 3. Scenario selection principles

When selecting migration safety scenarios, prefer scenarios that are:

- already used or clearly representative of current product behavior,
- likely to break if imports, runtime wiring, or graph access changes,
- reproducible in local development and ideally CI,
- narrow enough to maintain,
- stable enough to provide a useful regression signal.

Avoid selecting scenarios that are:

- highly flaky,
- dependent on unstable third-party output with no stable invariants,
- experimental,
- difficult to run without extensive manual setup,
- too broad to diagnose when they fail.

---

## 4. Required safety harness scenarios

The following scenario classes must be defined before major package movement begins.

### 4.1 Critical CLI scenario

A representative CLI-driven flow that exercises real product logic.

This scenario should:

- use the currently supported CLI entrypoint,
- exercise meaningful orchestration rather than trivial command parsing,
- produce a result or artifact that can be validated,
- remain runnable after packaging changes.

#### To define

- scenario name,
- command,
- required environment/config,
- required input data,
- expected output or invariants,
- failure conditions.

---

### 4.2 Critical API scenario

This scenario is required only if an API/backend is currently an active product boundary.

It should:

- exercise a real application path through the API boundary,
- validate contract-level behavior rather than only transport startup,
- confirm that interface wiring still resolves correctly,
- provide stable observable success criteria.

#### To define

- scenario name,
- endpoint,
- request shape,
- required environment/config,
- expected response invariants,
- failure conditions.

---

### 4.3 Critical graph retrieval scenario

A scenario that confirms graph-backed retrieval behavior remains functional.

This should validate at least one meaningful retrieval path involving Neo4j-backed access.

Examples of suitable invariants include:

- expected entity/category presence,
- expected retrieval count bounds,
- expected graph path or relationship category presence,
- expected no-error execution for a known graph-backed query.

#### To define

- scenario name,
- entrypoint,
- graph preconditions,
- retrieval input,
- expected invariants,
- failure conditions.

---

### 4.4 Critical answer/citation scenario

A scenario that confirms answer assembly and citation behavior remain structurally intact.

Because LLM outputs may vary, this scenario should focus on stable invariants rather than exact text matching unless exact matching is realistic.

Suitable invariants may include:

- response produced successfully,
- required citation objects/links/metadata are present,
- expected output structure is preserved,
- mandatory fields are populated,
- known source references remain traceable.

#### To define

- scenario name,
- entrypoint,
- input prompt/query,
- required graph/data preconditions,
- expected output invariants,
- failure conditions.

---

### 4.5 Critical ingestion or enrichment scenario

This scenario is required only if ingestion or enrichment is part of the active product path during restructuring.

It should validate that a representative transformation or graph-write path still works at a functional level.

Suitable invariants may include:

- expected nodes/edges/artifacts created,
- expected transformation completed,
- expected metadata written,
- expected no-error execution through the core path.

#### To define

- scenario name,
- entrypoint,
- required inputs,
- graph/data preconditions,
- expected invariants,
- failure conditions.

---

## 5. Golden-path scenario definitions

At least one golden-path scenario must be chosen for before/after comparison during early migration phases.

A golden-path scenario should be:

- representative,
- repeatable,
- narrow enough to diagnose,
- important enough that breakage would matter.

Golden-path scenarios do **not** require exact string equality if the system includes non-deterministic LLM behavior.  
Instead, they should validate stable invariants.

### 5.1 Golden-path scenario template

Use the following template for each golden-path scenario.

#### Scenario
- **Name:**
- **Purpose:**
- **Entrypoint:**
- **Command or request:**
- **Preconditions:**
- **Inputs:**
- **Expected invariants:**
- **Artifacts produced:**
- **How baseline is captured:**
- **Failure conditions:**
- **Owner:**

### 5.2 Baseline capture guidance

The baseline for a golden-path scenario should capture whichever signals are stable enough to be useful, such as:

- structured response fields,
- citation presence/shape,
- retrieval result invariants,
- artifact existence,
- graph mutation counts or categories,
- contract-level output schema.

Avoid relying on:

- unstable token-for-token LLM output,
- incidental logging content,
- timestamps or run IDs unless normalized,
- incidental ordering if ordering is not contractually meaningful.

### 5.3 Initial golden-path candidates

The team should select at least one initial candidate from among:

- a representative retrieval + answer + citation flow,
- a representative graph-backed query flow,
- a representative ingestion-to-graph materialization flow,
- a representative API request that exercises graph-backed answering.

Mark the chosen initial scenario explicitly once decided.

---

## 6. Neo4j-backed integration path requirement

At least one real Neo4j-backed integration path must exist before large structural movement begins.

This is required because mocked-only checks will not adequately protect against breakage in:

- graph driver/session wiring,
- query execution,
- retrieval semantics,
- graph-backed answer support,
- graph-dependent citation behavior.

### 6.1 Minimum requirements

The initial integration path must:

- exercise real Neo4j connectivity,
- exercise at least one real graph-backed application behavior,
- be runnable with documented setup,
- produce a pass/fail signal that is not purely manual.

### 6.2 Acceptable first integration targets

An acceptable first integration path may validate one of:

- graph retrieval,
- graph-backed enrichment,
- graph-backed citation assembly,
- graph-supported answer generation,
- ingestion that results in graph writes visible to a follow-up query.

### 6.3 Preconditions to document

For the selected integration path, document:

- required Neo4j environment,
- data/seed prerequisites,
- setup/reset instructions,
- command or test invocation,
- expected invariants,
- known sources of non-determinism.

---

## 7. Package and import validation

Before code movement begins, the team must be able to prove the system is running through the intended package/import path.

The purpose of this check is to prevent false confidence caused by:

- repo-root import accidents,
- path hacks,
- legacy entrypoint assumptions,
- environment-specific import behavior.

### 7.1 Minimum acceptable validation

At least one reproducible validation mechanism must exist, such as:

- CI install + smoke command,
- local install + smoke command documented in the repo,
- import validation script that confirms package-root execution,
- test invocation that fails if package wiring is broken.

### 7.2 Validation should confirm

The validation should confirm that:

- the package installs successfully,
- intended entrypoints run through installed/imported package code,
- imports do not depend on undeclared repo-root behavior,
- restructuring work does not silently bypass package boundaries.

---

## 8. Behavior preserved definition for early migration

For the purposes of early restructuring, behavior is considered preserved if:

- the selected critical scenarios still execute successfully,
- required outputs or artifacts are still produced,
- graph-backed behavior remains functionally available,
- no contract-breaking regressions are introduced in active paths,
- any differences are documented and intentionally accepted.

### 8.1 Differences that may be acceptable

These may be acceptable if documented and reviewed:

- internal file moves,
- internal import path changes,
- logging/output wording changes that do not affect contracts,
- non-user-facing naming cleanup,
- normalized artifact locations,
- acceptable changes in non-deterministic response wording where invariants still hold.

### 8.2 Differences that are not acceptable

These should block progress unless explicitly approved:

- broken active CLI/API paths,
- missing or malformed citation structures where required,
- loss of graph-backed functionality,
- import behavior that works only through accidental path setup,
- untracked compatibility shims,
- silent contract changes,
- failures in the required Neo4j-backed integration path.

---

## 9. Scenario inventory

Use this section to record the initial selected scenarios.

Initial dataset strategy for Phase 1:

- Primary baseline dataset: `demo_dataset_v1`
- Companion run-isolation dataset: `demo_dataset_v2`
- In this multi-dataset repository, baseline commands should use explicit dataset selection (`--dataset <name>` or `FIXTURE_DATASET=<name>`) to avoid ambiguous dataset resolution.

Accepted execution posture for Phase 1:

- Python 3.11+ is required.
- The validated model posture is `gpt-5.4`.
- The accepted automation entrypoint is `make phase1-verify` or `bash scripts/phase1_verify.sh`.
- The accepted CLI execution path uses module invocation (`python -m demo.run_demo ...`) throughout.

### 9.1 CLI scenario

- **Name:** Canonical demo CLI retrieval-and-answer flow
- **Purpose:** Verify that the active product path (`demo/` CLI orchestration) still executes end-to-end through retrieval and answer generation after package/import movement.
- **Entrypoint:** `python -m demo.run_demo`
- **Command:** Accepted canonical sequence:
	- `python -m demo.reset_demo_db --confirm`
	- `python -m demo.run_demo ingest-pdf --live --dataset demo_dataset_v1`
	- `export UNSTRUCTURED_RUN_ID="<run_id from ingest-pdf output>"`
	- `python -m demo.run_demo extract-claims --live --dataset demo_dataset_v1`
	- `python -m demo.run_demo resolve-entities --live --dataset demo_dataset_v1`
	- `python -m demo.run_demo ask --live --dataset demo_dataset_v1 --run-id "$UNSTRUCTURED_RUN_ID" --question "What does the document say about Endeavor and MercadoLibre?"`
- **Preconditions:**
	- Python 3.11+ is used,
	- required environment variables and model/provider credentials are configured,
	- `OPENAI_MODEL` is unset or explicitly set to `gpt-5.4`,
	- Neo4j is reachable,
	- dataset selection is explicit (`--dataset <name>` or `FIXTURE_DATASET=<name>`) when multiple datasets are present,
	- `UNSTRUCTURED_RUN_ID` is captured from `ingest-pdf` output for downstream commands.
- **Inputs:** One representative query already used in runbook validation.
- **Expected invariants:**
	- each command exits successfully,
	- retrieval and answer flow completes,
	- citation-grounded output structure appears on `ask`,
	- no repo-root-only import hack is required.
- **Artifacts produced:** Run manifests under `demo/artifacts/runs/<run_id>/...` and optional comparison artifacts under `demo/artifacts_compare/...`.
- **How baseline is captured:** Capture command sequence, dataset selection, run id, and manifest-level invariants (not exact LLM wording).
- **Failure conditions:**
	- stage command fails,
	- retrieval/answer stage does not complete,
	- expected citation structure is missing,
	- flow only works through accidental import path behavior.
- **Owner:** Ash

### 9.2 API scenario

- **Name:** Candidate backend API answer endpoint flow
- **Required:** no (current repository state indicates `backend/` is scaffolding and not connected to the active demo pipeline)
- **Purpose:** Document API non-gating status for Phase 1 while preserving a future slot for API safety checks once backend integration is active.
- **Endpoint:** Current placeholder endpoints are `/health` and `/graph/status` (`/graph/status` is intentionally HTTP 503).
- **Request shape:** N/A for Phase 1 gating (no active graph-backed answer endpoint).
- **Preconditions:** Backend starts for health/scaffold verification only.
- **Inputs:** Optional GET request to `/health`.
- **Expected invariants:**
	- backend process can start,
	- `/health` returns success,
	- `/graph/status` remains explicit placeholder behavior (503) until real integration is implemented.
- **Artifacts produced:** Optional HTTP response payloads and startup logs.
- **How baseline is captured:** Record that API is non-required for first-pass migration safety because active product behavior currently runs through `demo/` CLI.
- **Failure conditions:**
	- this scenario is incorrectly treated as a gating product-path check before backend integration exists,
	- placeholder behavior is mistaken for fully integrated graph-backed API readiness.
- **Owner:** Ash

### 9.3 Graph retrieval scenario

- **Name:** Canonical Neo4j-backed retrieval smoke path (`ask` baseline)
- **Purpose:** Verify graph-backed retrieval behavior survives import/runtime changes in the active demo path.
- **Entrypoint:** `python -m demo.run_demo ask --live --dataset demo_dataset_v1 --run-id "$UNSTRUCTURED_RUN_ID"`
- **Graph preconditions:**
	- Neo4j instance is available,
	- known-good run exists (`UNSTRUCTURED_RUN_ID`),
	- expected lexical/claim/entity-resolution data exists for that run.
- **Inputs:** Representative query used in the runbook baseline.
- **Expected invariants:**
	- retrieval completes with non-empty hits for known-good data,
	- `retrieval_and_qa` manifest shows stable retrieval diagnostics for the explicit run scope,
	- no raw Neo4j driver/session initialization errors occur.
- **Artifacts produced:** `retrieval_and_qa` manifest under `demo/artifacts/runs/<run_id>/retrieval_and_qa/manifest.json` plus console output.
- **How baseline is captured:** Validate manifest fields and retrieval diagnostics structure rather than exact answer text.
- **Failure conditions:**
	- Neo4j connection failure,
	- retrieval unexpectedly empty for known-good query,
	- runtime/import wiring failure in retrieval path,
	- manifest retrieval-path structure missing or malformed.
- **Owner:** Ash

### 9.4 Answer/citation scenario

- **Name:** Canonical citation-grounded answer flow (`ask` baseline)
- **Purpose:** Verify that answer assembly still produces citation-grounded outputs in the active demo query path.
- **Entrypoint:** `python -m demo.run_demo ask --live --run-id "$UNSTRUCTURED_RUN_ID"`
- **Input:** Representative validation question from runbook.
- **Preconditions:**
	- retrieval path is functioning,
	- Neo4j is reachable,
	- model/provider access is configured,
	- run scope is explicit (`--run-id`).
- **Expected invariants:**
	- answer is produced,
	- citation/source structure is present,
	- manifest-level citation quality signals indicate fully cited output for known-good baseline (`all_answers_cited: true`, `citation_fallback_applied: false`, `citation_quality.evidence_level: "full"`).
- **Artifacts produced:** `retrieval_and_qa` manifest and answer output.
- **How baseline is captured:** Capture structural citation/result invariants and manifest fields, not exact natural-language wording.
- **Failure conditions:**
	- answer generation fails,
	- citation/source metadata missing or malformed,
	- output contract shape drifts unexpectedly.
- **Owner:** Ash

### 9.5 Ingestion/enrichment scenario

- **Name:** Candidate structured-ingest + hybrid-alignment enrichment path
- **Required:** no (current active product flow is unstructured-first; structured ingest is optional enrichment in current demo posture)
- **Purpose:** Keep an explicit optional regression check for enrichment paths without blocking Phase 1 on non-core flow.
- **Entrypoint:**
	- `python -m demo.run_demo ingest-structured --live`
	- `python -m demo.run_demo resolve-entities --live --resolution-mode hybrid`
- **Inputs:** Current fixture structured dataset (selected via `--dataset` or `FIXTURE_DATASET`).
- **Preconditions:**
	- Neo4j reachable,
	- unstructured run already established,
	- required structured fixture files present.
- **Expected invariants:**
	- structured ingest completes,
	- hybrid alignment runs and reports alignment breakdown,
	- clustering remains intact (`mentions_clustered == mentions_total` in known-good baseline).
- **Artifacts produced:** Structured ingest and entity-resolution manifests.
- **How baseline is captured:** Capture manifest-level invariants (`resolution_mode`, `aligned_clusters`, `clusters_pending_alignment`, warning posture).
- **Failure conditions:**
	- command failure,
	- expected enrichment outputs absent,
	- hybrid flow fails due to import/runtime wiring changes.
- **Owner:** Ash

### 9.6 Golden-path scenario

- **Name:** Selected unstructured-first retrieval -> answer -> citation golden path
- **Purpose:** Selected initial baseline scenario for before/after migration comparison because it exercises the current highest-value active flow.
- **Entrypoint:** Demo CLI path (`python -m demo.run_demo ...`)
- **Command or request:** Accepted canonical baseline sequence:
	- `python -m demo.reset_demo_db --confirm`
	- `python -m demo.run_demo ingest-pdf --live --dataset demo_dataset_v1`
	- `export UNSTRUCTURED_RUN_ID="<run_id from ingest-pdf output>"`
	- `python -m demo.run_demo extract-claims --live --dataset demo_dataset_v1`
	- `python -m demo.run_demo resolve-entities --live --dataset demo_dataset_v1`
	- `python -m demo.run_demo ask --live --dataset demo_dataset_v1 --run-id "$UNSTRUCTURED_RUN_ID" --question "What does the document say about Endeavor and MercadoLibre?"`
- **Preconditions:**
	- Python 3.11+ is used,
	- Neo4j available with known-good fixture dataset,
	- `OPENAI_MODEL` is unset or explicitly set to `gpt-5.4`,
	- credentials configured,
	- question known to succeed in current runbook.
- **Inputs:** One runbook question with known citation-grounded behavior.
- **Expected invariants:**
	- flow completes successfully,
	- retrieval is non-empty,
	- answer is produced,
	- citation/source structure is present,
	- manifest-level response shape remains stable,
	- citation-quality invariants hold for known-good baseline (`all_answers_cited: true`, `citation_fallback_applied: false`, `citation_quality.evidence_level: "full"`).
- **Artifacts produced:** Run manifests and answer output.
- **How baseline is captured:** Record stable manifest/result invariants and run metadata; avoid exact token-level answer matching.
- **Failure conditions:**
	- flow fails,
	- retrieval unexpectedly empty,
	- answer missing,
	- citation contract broken.
- **Owner:** Ash

### 9.7 Neo4j integration path

- **Name:** Accepted live Neo4j demo integration check
- **Required Neo4j environment:** Local Docker Compose Neo4j (`docker compose up -d neo4j`) or equivalent standard dev Neo4j environment.
- **Data/seed prerequisites:** Fixture dataset available (`demo/fixtures/datasets/<dataset_name>/...`), plus fresh graph reset before baseline capture.
- **Setup/reset instructions:** Accepted proven baseline from live Phase 1 evidence:
	- `python -m demo.reset_demo_db --confirm`
	- `python -m demo.run_demo ingest-pdf --live --dataset demo_dataset_v1`
	- `export UNSTRUCTURED_RUN_ID="<run_id from ingest-pdf output>"`
	- `python -m demo.run_demo extract-claims --live --dataset demo_dataset_v1`
	- `python -m demo.run_demo resolve-entities --live --dataset demo_dataset_v1`
	- `python -m demo.run_demo ask --live --dataset demo_dataset_v1 --run-id "$UNSTRUCTURED_RUN_ID" --question "What does the document say about Endeavor and MercadoLibre?"`
- **Command or test invocation:** The accepted local smoke is `make phase1-verify`, which runs the same module-invocation path and captures artifacts for baseline, companion, and isolation re-ask validation.
- **Expected invariants:**
	- Neo4j connection succeeds,
	- graph-backed retrieval executes,
	- retrieval returns non-empty results for known-good query,
	- downstream answer/citation step completes.
- **Known sources of non-determinism:**
	- LLM wording variation,
	- result ordering when ranking scores are close.
- **Owner:** Ash

### 9.8 Package/import validation

- **Validation mechanism:** Accepted local reproducible smoke command for Phase 1
- **Command:**
	- `make phase1-verify`
	- `bash scripts/phase1_verify.sh`
	- underlying runtime path uses `.venv/bin/python -m demo.run_demo ...` rather than script-path invocation.
- **What it confirms:**
	- entrypoint resolution is explicit and reproducible,
	- migration changes do not depend on accidental repo-root path leakage,
	- package/import validation strategy is ready to harden as soon as package foundation work lands.
- **Where documented:** This file, `docs/repository_restructure/repository_restructure_checklist.md`, and README/developer setup docs when canonical command is finalized.
- **Owner:** Ash

---

## 10. Phase 1 exit gate

Phase 1 should be considered complete only when all of the following are true:

- [x] critical CLI scenario is defined
- [x] critical API scenario is either defined or explicitly marked not required
- [x] critical graph retrieval scenario is defined
- [x] critical answer/citation scenario is defined
- [x] critical ingestion/enrichment scenario is either defined or explicitly marked not required
- [x] at least one golden-path scenario is selected
- [x] baseline capture method is documented
- [x] at least one Neo4j-backed integration path is documented and runnable
- [x] package/import validation method is documented
- [x] “behavior preserved” criteria are accepted by the team
- [x] scenario owners are assigned

Until these are complete, broad structural movement should be treated as premature.

---

## 11. Immediate next actions

- [x] confirm API scenario is `Required: no` — backend is scaffolding, not an active product boundary
- [x] confirm ingestion/enrichment is `Required: no` for first-pass Phase 1 gating, retained as optional validation
- [x] enumerate candidate critical flows — initial repo-informed scenario inventory documented in Section 9
- [x] choose the initial golden-path scenario — unstructured-first retrieval → answer → citation (Section 9.6)
- [x] finalize canonical entrypoint commands from scenario inventory with Phase 1 owner confirmation
- [x] confirm first runnable Neo4j integration baseline against local dev environment
- [x] finalize package/import validation command for Phase 1 local reproducibility; installed-package hardening remains a Phase 2 concern
- [x] assign owners for each scenario inventory item
- [x] record accepted behavior-preservation criteria

Phase 1 gate status: closed. Remaining work moves to later phases and does not reopen Phase 1 execution proof.