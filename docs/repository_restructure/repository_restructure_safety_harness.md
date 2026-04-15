# Repository Restructure Safety Harness

Status: Draft  
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

### 9.1 CLI scenario

- **Name:** TBD
- **Purpose:** TBD
- **Entrypoint:** TBD
- **Command:** TBD
- **Preconditions:** TBD
- **Inputs:** TBD
- **Expected invariants:** TBD
- **Artifacts produced:** TBD
- **How baseline is captured:** TBD
- **Failure conditions:** TBD
- **Owner:** TBD

### 9.2 API scenario

- **Name:** TBD
- **Required:** TBD (`yes` / `no`)
- **Purpose:** TBD
- **Endpoint:** TBD
- **Request shape:** TBD
- **Preconditions:** TBD
- **Inputs:** TBD
- **Expected invariants:** TBD
- **Artifacts produced:** TBD
- **How baseline is captured:** TBD
- **Failure conditions:** TBD
- **Owner:** TBD

### 9.3 Graph retrieval scenario

- **Name:** TBD
- **Purpose:** TBD
- **Entrypoint:** TBD
- **Graph preconditions:** TBD
- **Inputs:** TBD
- **Expected invariants:** TBD
- **Artifacts produced:** TBD
- **How baseline is captured:** TBD
- **Failure conditions:** TBD
- **Owner:** TBD

### 9.4 Answer/citation scenario

- **Name:** TBD
- **Purpose:** TBD
- **Entrypoint:** TBD
- **Input:** TBD
- **Preconditions:** TBD
- **Expected invariants:** TBD
- **Artifacts produced:** TBD
- **How baseline is captured:** TBD
- **Failure conditions:** TBD
- **Owner:** TBD

### 9.5 Ingestion/enrichment scenario

- **Name:** TBD
- **Required:** TBD (`yes` / `no`)
- **Purpose:** TBD
- **Entrypoint:** TBD
- **Inputs:** TBD
- **Preconditions:** TBD
- **Expected invariants:** TBD
- **Artifacts produced:** TBD
- **How baseline is captured:** TBD
- **Failure conditions:** TBD
- **Owner:** TBD

### 9.6 Golden-path scenario

- **Name:** TBD
- **Purpose:** TBD
- **Entrypoint:** TBD
- **Command or request:** TBD
- **Preconditions:** TBD
- **Inputs:** TBD
- **Expected invariants:** TBD
- **Artifacts produced:** TBD
- **How baseline is captured:** TBD
- **Failure conditions:** TBD
- **Owner:** TBD

### 9.7 Neo4j integration path

- **Name:** TBD
- **Required Neo4j environment:** TBD
- **Data/seed prerequisites:** TBD
- **Setup/reset instructions:** TBD
- **Command or test invocation:** TBD
- **Expected invariants:** TBD
- **Known sources of non-determinism:** TBD
- **Owner:** TBD

### 9.8 Package/import validation

- **Validation mechanism:** TBD (`CI command` / `local command` / `import validation script`)
- **Command:** TBD
- **What it confirms:** TBD
- **Where documented:** TBD
- **Owner:** TBD

---

## 10. Phase 1 exit gate

Phase 1 should be considered complete only when all of the following are true:

- [ ] critical CLI scenario is defined
- [ ] critical API scenario is either defined or explicitly marked not required
- [ ] critical graph retrieval scenario is defined
- [ ] critical answer/citation scenario is defined
- [ ] critical ingestion/enrichment scenario is either defined or explicitly marked not required
- [ ] at least one golden-path scenario is selected
- [ ] baseline capture method is documented
- [ ] at least one Neo4j-backed integration path is documented and runnable
- [ ] package/import validation method is documented
- [ ] “behavior preserved” criteria are accepted by the team
- [ ] scenario owners are assigned

Until these are complete, broad structural movement should be treated as premature.

---

## 11. Immediate next actions

- [ ] decide whether API scenario is required
- [ ] decide whether ingestion/enrichment scenario is required
- [ ] enumerate candidate critical flows
- [ ] choose the initial golden-path scenario
- [ ] define the first Neo4j-backed integration path
- [ ] define the package/import validation command
- [ ] assign owners for each initial scenario
- [ ] record accepted behavior-preservation criteria