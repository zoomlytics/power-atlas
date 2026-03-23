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
| `match_method` | STRING | `raw_exact` / `casefold_exact` / `normalized_exact` |
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

## 7) Deferred Decisions

The following are explicitly not decided in this ADR and should be addressed
in future versions:

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

## 8) Alignment to Architectural Principles

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

## Closing Note

This ADR is the canonical record of the v0.3 claim argument model decision.
Any downstream code that reads or writes participation edges should reference
the `:HAS_PARTICIPANT {role}` pattern as authoritative. The v0.2 edge types
(`HAS_SUBJECT_MENTION`, `HAS_OBJECT_MENTION`) are retired and should be
treated as stale in any graph written before this version.

For the retrieval semantics that build on this model — including how participation
edges outrank chunk co-location and how cluster/canonical enrichments are treated
as provisional evidence — see
[retrieval-semantics-v0.1.md](retrieval-semantics-v0.1.md).
