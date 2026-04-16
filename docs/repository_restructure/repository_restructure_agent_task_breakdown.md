# Phase 1 Local-Agent Task Breakdown

**Repo:** `zoomlytics/power-atlas`  
**Date context:** `2026-04-15`  
**Phase owner:** Ash  
**Execution posture:** demo-first / CLI-first / Neo4j-backed  
**Golden path:** unstructured-first retrieval -> answer -> citation  
**Primary baseline dataset:** `demo_dataset_v1`  
**Companion run-isolation dataset:** `demo_dataset_v2`

## Checkpoint note

Phase 1 is complete and this document should now be read as an execution record
for the accepted Phase 1 posture, not as the current canonical next-task list for
repository restructuring.

As of 2026-04-16, the repository has already moved into compatibility-preserving
Phase 2 package-foundation work:

- `src/power_atlas/`, packaging metadata, bootstrap, and typed settings are present,
- package/import proof exists and editable install has been re-verified,
- multiple contract modules have been promoted into `src/power_atlas/contracts/`,
- `demo/contracts` remains intentional compatibility surface rather than the
   package-native target.

Use the checklist and decision register for current Phase 2 status and follow-up
sequencing.

## Purpose

This document turns the accepted repository restructure plan into a practical execution sequence for locally orchestrated coding agents.

The immediate Phase 1 goal is to:

1. prove the documented golden path in the live repo,
2. capture execution evidence,
3. identify doc/code/runtime drift,
4. validate run isolation behavior, and
5. choose the smallest safe automation target.

This is intended to support execution, not reopen architecture planning.

## Execution principles

- Prefer proof-by-execution over additional planning.
- Treat `demo/` as the active product core for Phase 1.
- Treat `backend/` and `frontend/` as non-critical placeholder/scaffolding surfaces for first-pass migration safety.
- Use the accepted documentation set as the starting source of truth.
- Validate commands against repo reality before changing docs.
- Keep scope tight: baseline proof, isolation proof, artifact capture, defect queue.
- Avoid broad refactors during initial execution unless required to remove a concrete blocker.
- Continue to use module invocation style during Phase 1:
  - `python -m demo.run_demo ...`
- Keep package/import validation at the Phase 1 level (reproducible command proof only); defer installed-package hardening to later phases.
- Do not expand Phase 1 scope to API-first gating or broader packaging work unless necessary to complete the baseline proof.

## Canonical input documents

All agents should use the following docs as shared context:

- `docs/repository_restructure/repository_restructure_plan.md`
- `docs/repository_restructure/repository_restructure_decisions.md`
- `docs/repository_restructure/repository_restructure_checklist.md`
- `docs/repository_restructure/repository_restructure_safety_harness.md`

## Alignment anchors

Use the following anchors to keep this task breakdown synchronized with accepted Phase 1 controls:

- `repository_restructure_checklist.md` Section 3 (Phase 1 safety harness definition)
- `repository_restructure_checklist.md` Section 4 (Do not start package movement until...)
- `repository_restructure_safety_harness.md` Section 9 (Scenario inventory)
- `repository_restructure_safety_harness.md` Section 10 (Phase 1 exit gate)

If this document and an anchor disagree, treat the anchor as canonical and log a doc-drift item for Agent E.

## Shared execution assumptions

### Active product path
The active product path for Phase 1 is `demo/`.

### Selected golden path
The selected initial golden path is:

**unstructured-first retrieval -> answer -> citation**

through the demo CLI path.

### Dataset posture
The selected Phase 1 dataset strategy is:

- **Primary baseline dataset:** `demo_dataset_v1`
- **Companion run-isolation dataset:** `demo_dataset_v2`

Dataset selection should remain explicit in multi-dataset mode.

### Command posture
Use documented dataset-scoped command sequences, including:

- explicit `--dataset demo_dataset_v1` where applicable,
- explicit capture/export of `UNSTRUCTURED_RUN_ID` after ingest,
- explicit `--run-id` on `ask` commands,
- reset included directly in the selected golden-path sequence.

For command truth, use `docs/repository_restructure/repository_restructure_safety_harness.md` Section 9.6 and Section 9.7 as the baseline source, then validate against current repo reality.

### Current non-goals
The following are not first-pass Phase 1 goals unless needed to remove a blocker:

- rewrite,
- API-first gating,
- ingestion/enrichment as required gating,
- installed-package validation hardening,
- broader package-structure completion,
- migration of placeholder `backend/` or `frontend/` surfaces into primary runtime status.

## Global exit criteria

This task breakdown is considered successful when:

1. the documented golden path is verified against current repo reality,
2. the baseline path is run manually at least once,
3. the companion run-isolation path is run manually at least once,
4. run IDs and artifacts are captured,
5. doc/code drift is recorded clearly, and
6. the smallest useful first automation target is chosen.

These completion criteria are the execution-layer companion to the formal Phase 1 gates in:

- `docs/repository_restructure/repository_restructure_safety_harness.md` Section 10
- `docs/repository_restructure/repository_restructure_checklist.md` Section 4

## Recommended agent topology

Recommended minimum agent split:

1. **Agent A - Command/Repo Reality Check**
2. **Agent B - Baseline Golden-Path Runner**
3. **Agent C - Run-Isolation Runner**
4. **Agent D - Artifact and Harness Prep**
5. **Agent E - Defect Triage and Fix Queue**

If fewer agents are available, combine work as follows:

- combine **Agent A + Agent D**
- combine **Agent B + Agent C**
- keep **Agent E** separate if possible

---

## Agent A - Command/Repo Reality Check

### Mission

Validate that the documented Phase 1 commands and assumptions still match the current repository and active code paths.

### Why this agent exists

Before spending time on repeated execution attempts, we need a fast confirmation pass that the docs are still aligned with actual entrypoints, flags, configuration expectations, and runtime dependencies.

### Inputs

- the four repository restructure docs,
- the current repository state,
- the `demo/` runtime path,
- CLI entrypoint definitions,
- argparse/click/typer wiring if present,
- Make targets if present,
- environment/config examples,
- Neo4j configuration surfaces,
- any repo scripts used in the golden path.

### Tasks

1. Confirm the active execution path is still rooted in `demo/`.
2. Locate the actual CLI/module entrypoints used by:
   - reset,
   - ingest,
   - ask,
   - citation/output steps on the golden path.
3. Confirm whether `python -m demo.run_demo ...` remains valid and canonical.
4. Verify dataset-selection flags/options are implemented as documented.
5. Verify explicit `--run-id` usage is supported where the docs require it.
6. Identify required environment variables, config files, and service dependencies.
7. Confirm the Neo4j operational setup required for the documented path.
8. Confirm that API and ingestion/enrichment are handled with the same gating posture documented in the safety harness (`Required: no` for first-pass Phase 1 gating unless repo reality changed).
9. Note any mismatches between docs and repo reality.
10. Separate:
   - true blockers,
   - harmless naming/config drift,
   - later hardening opportunities.

### Deliverable

A short **command reality check** report containing:

- **Confirmed entrypoints**
- **Required prerequisites**
- **Confirmed flags/options**
- **Doc/code mismatches**
- **Execution blockers**
- **Recommended corrections before baseline run**
- **Checklist/safety-harness gate-impact note** (what changes are needed, if any, to keep Phase 1 gates accurate)

### Definition of done

This agent is done when Ash can answer:

- What exact commands should we run?
- What must be configured first?
- What, if anything, in the docs is stale enough to block execution?

### Escalate immediately if

- the `demo/` path is no longer operational,
- documented commands are materially wrong,
- run-id selection is missing or broken,
- dataset selection is ambiguous,
- Neo4j dependency is undocumented and blocks first execution.

---

## Agent B - Baseline Golden-Path Runner

### Mission

Run the documented baseline scenario end-to-end using `demo_dataset_v1` and capture the first execution evidence set.

### Why this agent exists

This is the primary proof that the selected Phase 1 golden path is runnable in practice.

### Inputs

- Agent A findings,
- canonical safety harness commands,
- baseline dataset: `demo_dataset_v1`.

### Tasks

1. Prepare the environment according to confirmed prerequisites.
2. Execute the documented reset sequence.
3. Run the baseline ingest flow using explicit dataset selection for `demo_dataset_v1`.
4. Capture the produced `UNSTRUCTURED_RUN_ID`.
5. Run the documented ask flow using:
   - explicit `--dataset demo_dataset_v1`,
   - explicit `--run-id`.
6. Confirm the flow reaches:
   - retrieval,
   - answer,
   - citation output.
7. Save command transcripts and outputs.
8. If the run fails:
   - capture the exact failing step,
   - preserve stdout/stderr,
   - classify the failure as env, data, CLI, or runtime.

### Required evidence to capture

- commit SHA used,
- date/time,
- exact commands run,
- resolved dataset name,
- produced run ID,
- output files/logs/screenshots if used,
- whether result matched expected golden-path behavior.

### Deliverable

A baseline execution record with one of the following statuses:

- **PASS** - end-to-end baseline worked
- **PARTIAL** - some steps worked, but a blocker interrupted completion
- **FAIL** - baseline could not be meaningfully executed

### Definition of done

This agent is done when either:

- the baseline works end-to-end and evidence is saved, or
- the first blocking failure is documented precisely enough for remediation.

### Escalate immediately if

- ingest completes but run ID cannot be captured,
- ask cannot target a specific run,
- citations are absent when they should appear,
- command success masks incorrect dataset/run selection,
- reset is destructive or inconsistent in undocumented ways.

---

## Agent C - Run-Isolation Runner

### Mission

Validate that the companion dataset scenario works and that run/dataset isolation is explicit and reliable.

### Why this agent exists

The Phase 1 safety posture intentionally depends on using two related datasets to prove isolation behavior rather than assuming it.

### Inputs

- Agent A findings,
- baseline run evidence from Agent B,
- companion dataset: `demo_dataset_v2`.

### Tasks

1. Run the documented ingest flow for `demo_dataset_v2`.
2. Capture the companion run ID separately from the baseline run ID.
3. Execute ask commands against:
   - baseline dataset/run,
   - companion dataset/run.
4. Confirm command targeting remains explicit and unambiguous.
5. Inspect outputs for signs of cross-run or cross-dataset leakage.
6. Record whether the system behavior demonstrates:
   - correct isolation,
   - ambiguous selection,
   - leakage,
   - inconsistent command semantics.

### Specific checks

- Does `--dataset demo_dataset_v1` plus baseline run ID behave predictably?
- Does `--dataset demo_dataset_v2` plus companion run ID behave predictably?
- If dataset and run ID disagree, what happens?
- Are defaults unsafe when multiple runs exist?
- Is operator intent obvious from command behavior?

### Deliverable

A run-isolation validation note containing:

- **Baseline run ID**
- **Companion run ID**
- **Isolation checks performed**
- **Observed behavior**
- **Leakage / ambiguity findings**
- **Recommended immediate safeguards**

### Definition of done

This agent is done when there is a clear answer to:

> Can operators safely and explicitly target the intended dataset/run in multi-dataset mode?

### Escalate immediately if

- results blend across runs,
- default selection is unstable,
- commands silently ignore dataset/run arguments,
- output correctness depends on undocumented operator guesswork.

---

## Agent D - Artifact and Harness Prep

### Mission

Prepare the smallest possible repeatable execution harness and artifact structure, without over-automating Phase 1.

### Why this agent exists

After the first manual proof, the next leverage point is lightweight repeatability, not a large framework.

### Inputs

- findings from Agents A, B, and C,
- current repo structure,
- current checklist and safety harness.

### Tasks

1. Propose a minimal artifact directory structure for Phase 1 runs.
2. Define what should always be captured for each execution:
   - commit SHA,
   - commands,
   - dataset,
   - run ID,
   - outputs,
   - failures.
3. Identify the smallest automation target that reduces execution risk.
4. Prefer one of:
   - a single reproducible baseline runner, or
   - a baseline + isolation runner with artifact capture.
5. Avoid introducing broad framework changes, heavy abstractions, or Phase 2 packaging work.
6. If appropriate, propose:
   - one script,
   - one Make target, or
   - one thin pytest/integration harness,
   but only if it mirrors the documented command path cleanly.

### Non-goals

- redesigning the runtime,
- introducing a new orchestration framework,
- adding speculative abstractions,
- optimizing for elegance over debuggability.

### Deliverable

A short recommendation memo containing:

- **Suggested artifact location**
- **Per-run artifact contract**
- **Best first automation target**
- **Why this is the smallest safe automation step**
- **What should explicitly wait until Phase 2**

### Definition of done

This agent is done when Ash can confidently choose the first automation unit without reopening architecture planning.

---

## Agent E - Defect Triage and Fix Queue

### Mission

Turn execution findings into a prioritized, low-noise remediation queue for Phase 1.

### Why this agent exists

Execution will expose drift and defects. We need a queue that helps Ash sequence fixes without expanding scope.

### Inputs

- outputs from Agents A-D.

### Tasks

1. Collect all discovered issues and normalize them into a single queue.
2. Classify each item into one of:
   - environment/setup,
   - documentation drift,
   - CLI/UX,
   - dataset handling,
   - run-id handling,
   - Neo4j operational dependency,
   - output/citation correctness,
   - artifact capture gap,
   - migration-boundary concern.
3. Assign each item a priority:
   - **P0** - blocks Phase 1 baseline proof
   - **P1** - blocks repeatable execution or isolation confidence
   - **P2** - important but can wait until after initial proof
   - **P3** - improvement, cleanup, or Phase 2 candidate
4. Recommend disposition:
   - fix now,
   - document now / fix later,
   - defer to Phase 2,
   - ignore for Phase 1.
5. Keep the queue execution-focused, not aspirational.

### Deliverable

A prioritized remediation queue.

### Definition of done

This agent is done when Ash has a sequenced list of what to fix next, with clear boundaries on what should not be pulled into Phase 1.

---

## Recommended execution order

### Step 1 - Agent A

Run **Agent A** first.

**Reason:** This is the cheapest way to prevent wasted execution effort and validate commands and prerequisites before runtime attempts.

### Step 2 - Agent B

Run **Agent B** next.

**Reason:** Baseline proof is the highest-value first execution result.

### Step 3 - Agent C

Run **Agent C** after baseline.

**Reason:** Run isolation is most meaningful once the baseline path is understood well enough to compare behavior.

### Step 4 - Agent D

Run **Agent D** after first manual evidence exists.

**Reason:** Automation should encode known-good operator behavior, not assumptions.

### Step 5 - Agent E

Run **Agent E** continuously or immediately after each execution cycle.

**Reason:** This prevents issue sprawl and keeps Phase 1 focused.

## Suggested handoff format between agents

Each agent should return results in the following compact structure.

### Handoff header

- **Agent name**
- **Date/time**
- **Repo**
- **Branch / commit SHA**
- **Status:** `PASS` / `PARTIAL` / `FAIL`

### Handoff body

- **What was attempted**
- **What was confirmed**
- **What failed or remains uncertain**
- **Evidence/artifact locations**
- **Recommended next action**
- **Escalations / blockers**

## Practical success criteria by agent

### Agent A success
- exact runnable commands are confirmed,
- prerequisites are known,
- blocking drift is identified.

### Agent B success
- `demo_dataset_v1` baseline path runs end-to-end,
  or the first failure is precisely isolated.

### Agent C success
- `demo_dataset_v1` vs `demo_dataset_v2` behavior is explicitly validated,
- isolation confidence is established or disproven.

### Agent D success
- one minimal automation target is selected,
- one artifact contract is defined.

### Agent E success
- defects are prioritized without broadening scope.

## Minimal coordination notes for Ash

Ash should act as:

- final arbiter of command truth,
- owner of go/no-go decisions,
- approver of any scope expansion beyond baseline proof,
- owner of the first automation choice.

Ash should specifically resist:

- premature package hardening,
- generalized framework cleanup,
- expanding Phase 1 to cover API or placeholder surfaces,
- solving future-architecture concerns before baseline proof exists.

## Immediate next action

Recommended immediate assignments:

1. assign **Agent A** to produce the command reality check,
2. assign **Agent B** to attempt the first `demo_dataset_v1` baseline run immediately after command truth is confirmed,
3. assign **Agent C** to prepare the `demo_dataset_v2` isolation pass once baseline execution is understood.

After the first execution cycle, run **Agent D** and **Agent E** to lock artifact capture and triage drift against the formal Phase 1 gates.

## Optional follow-on document

After first execution begins, create a lightweight **Phase 1 execution run log** to record:

- operator/agent,
- timestamp,
- commit SHA,
- dataset,
- commands run,
- run ID produced,
- expected result,
- actual result,
- artifact paths,
- issues encountered,
- follow-up action.