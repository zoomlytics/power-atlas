# Power Atlas — Claim Argument Model Decision (v0.3)

**Status:** Accepted  
**Audience:** Contributors, architects, reviewers  
**Scope:** v0.3 claim participation edge model (graph implementation layer)

---

## 1) Context

Power Atlas v0.2 introduced explicit participation edges that connect an
`:ExtractedClaim` to its `:EntityMention` arguments:

- `:HAS_SUBJECT_MENTION` — carries the subject of a claim
- `:HAS_OBJECT_MENTION` — carries the object of a claim

These edges carry provenance properties (`run_id`, `source_uri`,
`match_method`) and are written by the `claim-participation` pipeline stage.

Before extending claim argument support to additional use-cases anticipated in
v0.3–v0.4, this ADR documents an intentional review of the edge model and
records the chosen direction.

---

## 2) Anticipated v0.3–v0.4 Requirements

| Requirement | Detail |
|---|---|
| N-ary argument roles | Roles beyond subject/object: agent, location, value, recipient, etc. |
| Role-labelled retrieval | Retrieval queries must be able to ask "give me the agent of this claim" without fixed edge types |
| Temporal/qualifier arguments | Arguments that are not entity mentions (dates, values, literal qualifiers) |
| Non-entity objects | Objects that are scalar values or free-text slots, not resolvable to an `EntityMention` |
| Provenance on roles | Each role assignment must carry `match_method`, `run_id`, `source_uri` |
| Idempotent re-extraction | Re-running the stage must produce exactly the same edges (MERGE semantics) |

---

## 3) Options Evaluated

### Option A — Keep dual `:HAS_SUBJECT_MENTION` / `:HAS_OBJECT_MENTION` edges

**Pros:**
- No migration required; existing graphs are already valid.
- Simple Cypher: `(claim)-[:HAS_SUBJECT_MENTION]->(mention)`.
- Edge type encodes the role, so no property filtering needed.

**Cons:**
- Cannot be extended to N roles without adding new fixed edge types for every
  new role (`:HAS_AGENT_MENTION`, `:HAS_LOCATION_MENTION`, etc.).
- Schema becomes a sprawling list of edge type declarations.
- Queries that want "all arguments of a claim" must enumerate every edge type.
- Does not support non-entity arguments (scalar values, literals).
- Locks the ontology to a two-role subject/object assumption in the
  infrastructure layer, contradicting the Semantic Core independence principle.

### Option B — Generic `:HAS_PARTICIPANT` edge with `role` property

**Pros:**
- Single edge type for all claim arguments; `role` property carries the
  semantic label (`"subject"`, `"object"`, `"agent"`, `"location"`, etc.).
- Queries that want all arguments of a claim use
  `(claim)-[:HAS_PARTICIPANT]->(m)` with optional `WHERE r.role = ...`
  filtering.
- Adding new roles requires no schema change — only new `role` values.
- `MERGE (claim)-[r:HAS_PARTICIPANT {role: row.role}]->(mention)` is still
  idempotent: the `{role}` constraint in the MERGE key means subject and
  object get distinct edges.
- Consistent with provenance requirements: each edge still carries
  `match_method`, `run_id`, `source_uri`.

**Cons:**
- Requires a migration from v0.2 (existing `HAS_SUBJECT_MENTION` /
  `HAS_OBJECT_MENTION` graphs become stale after upgrade).
- Role filtering is a property predicate, not a type predicate — marginally
  more verbose in Cypher.
- `role` property must be part of the MERGE identity key (enforced by
  including it in the `{…}` map of the MERGE pattern), which is less
  immediately obvious than a distinct edge type.

### Option C — Intermediate argument/role nodes

Create a dedicated `:ClaimArgument` node between the claim and the mention:

```
(claim)-[:HAS_ARGUMENT]->(arg:ClaimArgument {role: "subject"})-[:REFERS_TO]->(mention)
```

**Pros:**
- Maximum future flexibility: argument nodes can carry their own properties,
  qualifiers, temporal scope, or scalar values.
- Supports non-entity arguments natively (argument node holds the value).

**Cons:**
- Significantly higher graph complexity: every participation edge doubles into
  two edges and one intermediate node.
- Traversals become two hops instead of one.
- Premature for v0.3: non-entity arguments and complex qualifiers are not yet
  required.
- Violates the "clarity over cleverness" architectural constraint.

---

## 4) Decision

**Option B — migrate to `:HAS_PARTICIPANT` with `role` property.**

Rationale:

1. **N-ary extensibility without schema changes.** New roles can be introduced
   by simply using new `role` values; no new edge type declarations are
   required.

2. **Semantic Core independence.** The implementation layer no longer hard-codes
   a two-role assumption. The `role` property is data, not schema.

3. **Clarity over cleverness.** A single edge type is simpler to reason about
   than a growing catalogue of `HAS_*_MENTION` types, while being less
   over-engineered than option C.

4. **Option C is deferred.** Intermediate argument nodes are not needed for v0.3
   requirements. They can be introduced in a future version if non-entity
   arguments (scalar values, temporal qualifiers) are required. The `:HAS_PARTICIPANT`
   model does not prevent this migration — it narrows the blast radius.

5. **Migration path is explicit.** v0.2 graphs are non-migratable (same
   non-migratable policy as the v0.1 → v0.2 transition). A full reset followed
   by a fresh pipeline run is the only supported upgrade path. The `demo-reset`
   command is updated to clean up stale v0.2 participation edges.

---

## 5) v0.3 Graph Model (Adopted)

### Participation edge

```
(claim:ExtractedClaim)-[r:HAS_PARTICIPANT]->(mention:EntityMention)
```

**Edge properties:**

| Property | Type | Description |
|---|---|---|
| `role` | STRING (MERGE key) | Semantic role: `"subject"`, `"object"`, or future values |
| `run_id` | STRING | Extraction run that produced this edge |
| `match_method` | STRING | `raw_exact` / `casefold_exact` / `normalized_exact` / `list_split` |
| `source_uri` | STRING? | Provenance URI for the source document |

**MERGE identity:** `(claim)-[r:HAS_PARTICIPANT {role: row.role}]->(mention)`

The `role` property is part of the MERGE key. This means a claim that has
both a subject and an object mention will have two distinct
`:HAS_PARTICIPANT` edges, each with a different `role` value.

### Representative Cypher queries

```cypher
// All arguments of a claim (any role)
MATCH (c:ExtractedClaim {claim_id: $id, run_id: $run_id})-[r:HAS_PARTICIPANT]->(m:EntityMention)
RETURN r.role, m.name, r.match_method

// Subject only
MATCH (c:ExtractedClaim {claim_id: $id, run_id: $run_id})-[r:HAS_PARTICIPANT {role: 'subject'}]->(m:EntityMention)
RETURN m.name

// Future: agent role (no schema change needed)
MATCH (c:ExtractedClaim {claim_id: $id, run_id: $run_id})-[r:HAS_PARTICIPANT {role: 'agent'}]->(m:EntityMention)
RETURN m.name
```

---

## 6) Migration

### v0.2 → v0.3 (non-migratable; full reset required)

v0.2 graphs contain `:HAS_SUBJECT_MENTION` and `:HAS_OBJECT_MENTION` edges.
These relationship types are retired in v0.3. Old graphs are **not migratable**.

**Upgrade path:**
1. Run `demo-reset` (clears all demo-owned nodes and their relationships).
2. Re-run the full pipeline: `ingest-pdf` → `extract-claims` → `resolve-entities`.

The `demo-reset` command is updated to detect and remove any surviving stale
participation edges from earlier versions, including both
`:HAS_SUBJECT_MENTION` / `:HAS_OBJECT_MENTION` (v0.2) and
`:HAS_SUBJECT` / `:HAS_OBJECT` (pre-v0.2) edges, and to report the total
count under `stale_participation_edges_deleted`.

### v0.1 → v0.2 cleanup (unchanged)

Stale `:HAS_SUBJECT` / `:HAS_OBJECT` edges (pre-v0.2) continue to be cleaned
up by this same `demo-reset` path and are included in
`stale_participation_edges_deleted`. No additional changes are required.

---

## 7) Composite Argument Form Boundaries

The `list_split` matching strategy handles composite slot values by splitting
them on recognized list separators.  The table below records the explicit
support decision for each form encountered in practice.

### Supported composite forms

| Form | Example | Behaviour |
|---|---|---|
| Conjunction (`and` / `or` / `&`) | `Amazon and eBay` | Splits; each part matched independently |
| Oxford-comma conjunction | `Amazon, eBay, and Google` | Splits; the `, and ` separator consumed as a unit |
| Comma-separated list | `Amazon, eBay, Google` | Splits on `", "` |
| **Slash-delimited list** | `Amazon / eBay / Google` | Splits on `" / "` (whitespace required on both sides) |
| **Semicolon-delimited list** | `Amazon; eBay; Google` | Splits on `"; "` (trailing whitespace required) |

Slash and semicolon separators require surrounding/trailing whitespace to
avoid false positives (URL paths, numeric ratios, abbreviations).

### Partial-recovery forms (supported via existing separators)

These patterns use already-supported separators.  The entity name is
recovered; the qualifying phrase fails to match and is silently skipped.
This is intentional: partial recovery is preferable to no recovery.

| Form | Example | Behaviour |
|---|---|---|
| Appositive phrase | `Xapo, a digital-assets company` | Comma split: `Xapo` matched, descriptor phrase discarded |
| Trailing qualifier in list | `Amazon, eBay, and Google subsidiaries` | `Amazon` and `eBay` matched; `Google subsidiaries` not resolved |

### Intentionally unsupported forms

The following patterns are explicitly **not** supported.  They produce partial
recovery at best; no special-purpose code is added to handle them.

| Form | Example | Why unsupported |
|---|---|---|
| Parenthetical qualifier | `Amazon (AWS) and Google` | `Amazon (AWS)` does not match mention `Amazon`; parenthetical stripping requires NLP |
| Grouped qualifier (shared suffix) | `Amazon and eBay subsidiaries` | `eBay subsidiaries` ≠ `eBay`; suffix removal is ambiguous |
| Shared-prefix qualifier | `U.S. and European regulators` | `European regulators` ≠ `European`; same issue |
| Bare slash | `Amazon/eBay` | Not split — could be URL path or ratio |
| Bare semicolon | `Amazon;eBay` | Not split — could be abbreviation |

### Architectural rationale

- **Precision over recall**: emitting an incorrect edge is worse than emitting
  no edge.  Unsupported forms that cannot be resolved without linguistic
  analysis are left unmatched rather than guessed at.
- **Deterministic and observable**: every match is reproducible from the same
  inputs; the `match_method = list_split` value on the edge records that
  list-splitting was used.
- **Unstructured-first posture**: complex qualifiers are structural enrichments
  that belong in future argument-parsing stages, not in the current
  deterministic text-matching layer.

---

## 8) Deferred Decisions

- **Non-entity arguments** (scalar values, date literals, free-text qualifiers):
  If v0.4+ requires arguments that are not `EntityMention` nodes, the
  intermediate-node model (option C) should be revisited. The current
  `:HAS_PARTICIPANT` model does not support pointing at arbitrary value types.

- **Temporal argument scoping**: Temporal qualifiers on individual argument
  slots are out of scope for v0.3. See
  [`/docs/architecture/temporal-modeling-v0.1.md`](/docs/architecture/temporal-modeling-v0.1.md)
  for the broader temporal modeling principles.

- **Confidence on argument assignments**: Confidence scores on individual
  participation edges (beyond `match_method`) are deferred to v0.4+.

---

## 9) Alignment to Architectural Principles

This decision reinforces:

- **Semantic Core independence**: role semantics live in data (`role` property),
  not in infrastructure (edge type names). Changing storage engines would not
  require redefining what "subject" means.
- **Evidence-first**: participation edges carry `match_method` and `source_uri`
  so that every role assignment is auditable.
- **Clarity over cleverness**: one edge type is simpler than N; two-hop
  intermediate nodes are deferred until genuinely required.
- **Non-destructive additions**: new roles can be added without altering
  existing edges or schema declarations.

---

## 10) Participation Matching Metrics

### Overview

Each pipeline run that executes the `claim-participation` stage produces two
artifacts under `<output_dir>/runs/<run_id>/claim_participation/`:

| File | Contents |
|---|---|
| `claim_participation_summary.json` | High-level run summary (edges written, role breakdown, embedded `match_metrics`) |
| `participation_metrics.json` | Full `ParticipationMatchMetrics` object for offline analysis |

Both files are written by `run_claim_participation` and are available
immediately after the stage completes.  In `dry_run` mode only the summary
is written (with `"match_metrics": null`).

### `ParticipationMatchMetrics` fields

| Field | Description |
|---|---|
| `claims_processed` | Total claim rows supplied to the matcher |
| `slots_processed` | (Claim, slot) pairs where slot text was non-empty and at least one candidate mention was available |
| `edges_by_method` | Edge count by `match_method` (`raw_exact` / `casefold_exact` / `normalized_exact` / `list_split`) |
| `edges_by_role` | Edge count by role (`subject` / `object`) |
| `edges_by_role_and_method` | Two-level breakdown: `{role: {match_method: count}}` |
| `unmatched_slots` | Slots that produced no edge and whose whole-slot attempt found no matching candidate mention |
| `unmatched_by_role` | `unmatched_slots` broken down by role |
| `ambiguous_slots` | Slots whose whole-slot attempt matched two or more candidates (`MATCH_OUTCOME_AMBIGUOUS`) |
| `ambiguous_by_role` | `ambiguous_slots` broken down by role |
| `list_split_suppressed` | Slots where list-split was not attempted because the whole-slot match was ambiguous (always equals `ambiguous_slots`) |
| `list_split_suppressed_by_role` | `list_split_suppressed` broken down by role |
| `claims_with_any_edge` | Claims with at least one participation edge emitted |
| `claims_with_no_edges` | `claims_processed` minus `claims_with_any_edge` |
| `sample_list_split_claim_ids` | Up to 20 claim IDs that contributed a `list_split` edge |
| `sample_unmatched_claim_ids` | Up to 20 claim IDs with at least one unmatched slot |
| `sample_ambiguous_claim_ids` | Up to 20 claim IDs with at least one ambiguous whole-slot match |

### Interpreting movement in metrics after pipeline changes

| Signal | Interpretation |
|---|---|
| `edges_by_method["list_split"]` increases | More composite/list-valued slots are now matched; verify samples are semantically correct |
| `unmatched_slots` decreases | Coverage improved; check whether precision was preserved |
| `ambiguous_slots` increases | More mention-name collisions; may indicate extraction producing redundant mentions |
| `list_split_suppressed` stays equal to `ambiguous_slots` | Architectural guardrail is intact — list-split is never attempted over ambiguous whole-slot matches |
| `claims_with_no_edges` decreases | More claims now have at least one linked argument mention |

### Suggested validation queries

```cypher
// Match-method distribution for a specific run
MATCH (:ExtractedClaim)-[r:HAS_PARTICIPANT]->(:EntityMention)
WHERE r.run_id = $run_id
RETURN r.match_method AS match_method, count(*) AS edges
ORDER BY edges DESC;
```

```cypher
// Claim edge-coverage distribution
MATCH (c:ExtractedClaim)
WHERE c.run_id = $run_id
OPTIONAL MATCH (c)-[r:HAS_PARTICIPANT]->(:EntityMention)
WITH c, count(r) AS participant_edges
RETURN participant_edges, count(*) AS claim_count
ORDER BY participant_edges;
```

```cypher
// Sample list_split results
MATCH (c:ExtractedClaim)-[r:HAS_PARTICIPANT]->(m:EntityMention)
WHERE c.run_id = $run_id
  AND r.match_method = 'list_split'
RETURN c.claim_id, c.claim_text, r.role, m.name, r.match_method
ORDER BY c.claim_id
LIMIT 100;
```

---

## Closing Note

This ADR is the canonical record of the v0.3 claim argument model decision.
Any downstream code that reads or writes participation edges should reference
the `:HAS_PARTICIPANT {role}` pattern as authoritative.  The v0.2 edge types
(`HAS_SUBJECT_MENTION`, `HAS_OBJECT_MENTION`) are retired and should be
treated as stale in any graph written before this version.

For the retrieval semantics that build on this model — including how participation
edges outrank chunk co-location and how cluster/canonical enrichments are treated
as provisional evidence — see
[retrieval-semantics-v0.1.md](retrieval-semantics-v0.1.md).
