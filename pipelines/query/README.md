# Neo4j Browser Query Workbook — Power Atlas v0.3

This workbook contains ready-to-run Cypher queries for exploring the Power Atlas graph in Neo4j Browser.
Paste any query block directly into the Neo4j Browser editor and run it.

**Recommended traversal patterns for v0.3:** start from claim-participation edges
(`HAS_PARTICIPANT` with `role` property), not chunk co-location.
Chunk co-location queries are still available for architecture-level inspection;
see [Architecture reference queries](#architecture-reference-queries-chunk-co-location) below.

For the design invariants that govern retrieval (chunk-first anchoring, participation-edge
precedence, provisional cluster/canonical enrichment, and citation anchoring at the chunk
level), see
[docs/architecture/retrieval-semantics-v0.1.md](../../docs/architecture/retrieval-semantics-v0.1.md).

---

## Quick-start: validate the graph is populated

```cypher
// Count nodes by label
MATCH (n)
UNWIND labels(n) AS label
RETURN label, count(*) AS total
ORDER BY total DESC;
```

```cypher
// Count relationship types
MATCH ()-[r]->()
RETURN type(r) AS rel_type, count(r) AS total
ORDER BY total DESC;
```

---

## 1. Claim-participation queries (v0.3 — recommended)

These queries traverse `HAS_PARTICIPANT` edges with `role` property filtering — the v0.3
participation model that directly links each `ExtractedClaim` to the `EntityMention` nodes
filling its argument slots.  Prefer these over chunk co-location for all claim-focused analysis.

> **Tip:** If multiple pipeline runs exist in the database, scope queries to a single run by
> setting a parameter in Neo4j Browser before running the queries below:
>
> ```cypher
> :param run_id => 'your-run-id-here'
> ```
>
> Then add `WHERE c.run_id = $run_id` (or `WHERE m.run_id = $run_id`) to any query as needed.

### 1a. Basic participation edge validation

```cypher
// Subject edges — check that HAS_PARTICIPANT {role: 'subject'} edges are present
MATCH (c:ExtractedClaim)-[r:HAS_PARTICIPANT {role: 'subject'}]->(m:EntityMention)
RETURN c.run_id, c.claim_id, c.claim_text, r.match_method, m.name
LIMIT 25;
```

```cypher
// Object edges — check that HAS_PARTICIPANT {role: 'object'} edges are present
MATCH (c:ExtractedClaim)-[r:HAS_PARTICIPANT {role: 'object'}]->(m:EntityMention)
RETURN c.run_id, c.claim_id, c.claim_text, r.match_method, m.name
LIMIT 25;
```

```cypher
// Combined edge summary — one row per role (all runs)
MATCH ()-[r:HAS_PARTICIPANT]->()
RETURN r.role AS role, count(r) AS total
ORDER BY role;
```

```cypher
// Full claim view — subject AND object mentions together
MATCH (subj:EntityMention)<-[sr:HAS_PARTICIPANT {role: 'subject'}]-(c:ExtractedClaim)-[obj_r:HAS_PARTICIPANT {role: 'object'}]->(obj:EntityMention)
RETURN c.run_id,
       c.claim_id,
       subj.name       AS subject_mention,
       c.predicate     AS predicate,
       obj.name        AS object_mention,
       c.claim_text,
       sr.match_method AS subject_match,
       obj_r.match_method AS object_match
LIMIT 25;
```

**Interpretation notes (v0.3):**

- `role` records which argument slot the mention fills: `"subject"`, `"object"`, or a future
  role value like `"agent"`, `"location"`, etc.
- `match_method` records how the slot text was resolved to a mention:
  `raw_exact` → identical text (highest confidence), `casefold_exact` → case-insensitive match,
  `normalized_exact` → Unicode-normalized match (NFKD + diacritic removal, apostrophe/hyphen normalization, runs of whitespace collapsed, and case-folded).
- A claim may have a subject edge, an object edge, both, or neither, depending on whether the
  extraction LLM populated those slots and whether a unique matching mention was found.
- Claims with no participation edges are still valid assertion nodes; they simply lacked a
  resolvable match in the same chunk.

---

## 2. Entity-centric claim search

These queries answer: *"Which claims involve this entity as subject or object?"*

### 2a. Signature query — Marcos Galperin

```cypher
// All claims where Marcos Galperin appears as subject
MATCH (c:ExtractedClaim)-[r:HAS_PARTICIPANT {role: 'subject'}]->(m:EntityMention)
WHERE toLower(m.name) CONTAINS 'galperin'
RETURN c.claim_text, c.predicate, c.object, m.name AS matched_mention, r.match_method
ORDER BY c.claim_id;
```

```cypher
// All claims where Marcos Galperin appears as subject OR object
MATCH (c:ExtractedClaim)-[r:HAS_PARTICIPANT]->(m:EntityMention)
WHERE toLower(m.name) CONTAINS 'galperin'
RETURN c.claim_text, r.role AS role, m.name AS matched_mention, r.match_method
ORDER BY c.claim_id;
```

### 2b. Signature query — MercadoLibre

```cypher
// All claims where MercadoLibre appears as subject
MATCH (c:ExtractedClaim)-[r:HAS_PARTICIPANT {role: 'subject'}]->(m:EntityMention)
WHERE toLower(m.name) CONTAINS 'mercadolibre'
RETURN c.claim_text, c.predicate, c.object, m.name AS matched_mention, r.match_method
ORDER BY c.claim_id;
```

```cypher
// All claims where MercadoLibre appears in any role
MATCH (c:ExtractedClaim)-[r:HAS_PARTICIPANT]->(m:EntityMention)
WHERE toLower(m.name) CONTAINS 'mercadolibre'
RETURN c.claim_text, r.role AS role, m.name AS matched_mention, r.match_method
ORDER BY c.claim_id;
```

### 2c. General entity search

```cypher
// Replace 'endeavor' with any entity name fragment you want to search
MATCH (c:ExtractedClaim)-[r:HAS_PARTICIPANT]->(m:EntityMention)
WHERE toLower(m.name) CONTAINS 'endeavor'
RETURN c.claim_text, r.role AS role, m.name AS matched_mention, r.match_method
ORDER BY c.claim_id;
```

**Validation guidance:**

After running the full demo with the default unstructured PDF fixture, the signature queries
for `galperin` and `mercadolibre` should each return at least one row.  If they return no
results, verify that:

1. `extract-claims` completed successfully (check the manifest for `extracted_claim_count > 0`).
2. The claim-participation stage ran:
   - If you ran the full demo or `extract-claims` as part of the batch pipeline, check for
     `subject_edges > 0` or `object_edges > 0` in `claim_participation_summary.json` (or in
     the top-level `manifest.json` in batch mode).
   - If you ran claim-participation as an independent stage, check for `subject_edges > 0` or
     `object_edges > 0` in `runs/<run_id>/claim_participation/claim_participation_summary.json`.
   - Alternatively, re-run `extract-claims`, which includes participation in the same pass.
3. The graph has not been reset since the last `extract-claims` run.

---

## 3. Pairwise claim analysis

These queries answer: *"Which claims connect entity A to entity B?"*

### 3a. Signature pairwise — Marcos Galperin ↔ MercadoLibre

```cypher
// Claims where Marcos Galperin is subject and MercadoLibre is object
MATCH (subj:EntityMention)<-[:HAS_PARTICIPANT {role: 'subject'}]-(c:ExtractedClaim)-[:HAS_PARTICIPANT {role: 'object'}]->(obj:EntityMention)
WHERE toLower(subj.name) CONTAINS 'galperin'
  AND toLower(obj.name)  CONTAINS 'mercadolibre'
RETURN c.claim_text, c.predicate, subj.name AS subject, obj.name AS object;
```

```cypher
// Claims connecting Galperin and MercadoLibre in either direction
MATCH (a:EntityMention)<-[:HAS_PARTICIPANT {role: 'subject'}]-(c:ExtractedClaim)-[:HAS_PARTICIPANT {role: 'object'}]->(b:EntityMention)
WHERE (toLower(a.name) CONTAINS 'galperin'    AND toLower(b.name) CONTAINS 'mercadolibre')
   OR (toLower(a.name) CONTAINS 'mercadolibre' AND toLower(b.name) CONTAINS 'galperin')
RETURN c.claim_text, c.predicate, a.name AS subject, b.name AS object
ORDER BY c.claim_id;
```

### 3b. General pairwise — any two entities

```cypher
// Replace the two CONTAINS filters with the entity names you want to compare
MATCH (a:EntityMention)<-[:HAS_PARTICIPANT {role: 'subject'}]-(c:ExtractedClaim)-[:HAS_PARTICIPANT {role: 'object'}]->(b:EntityMention)
WHERE (toLower(a.name) CONTAINS 'endeavor' AND toLower(b.name) CONTAINS 'mercadolibre')
   OR (toLower(a.name) CONTAINS 'mercadolibre' AND toLower(b.name) CONTAINS 'endeavor')
RETURN c.claim_text, c.predicate, a.name AS subject, b.name AS object
ORDER BY c.claim_id;
```

### 3c. All pairwise claim links (sample)

```cypher
// All claims that have both subject and object mentions — shows the full pairwise graph
MATCH (a:EntityMention)<-[:HAS_PARTICIPANT {role: 'subject'}]-(c:ExtractedClaim)-[:HAS_PARTICIPANT {role: 'object'}]->(b:EntityMention)
RETURN a.name AS subject_entity,
       c.predicate,
       b.name AS object_entity,
       c.claim_text
LIMIT 25;
```

**Interpretation notes:**

- Pairwise queries require *both* a subject and an object `HAS_PARTICIPANT` edge to be present on
  the same claim.  If one slot is missing (no unique mention match found), the claim will not
  appear in the result.
- To include claims where only one slot was resolved, use the entity-centric queries in section 2
  which match any role independently.

---

## 4. Cluster-aware entity traversal (post-hybrid)

These queries apply after `resolve-entities --resolution-mode hybrid` has run.

> **Post-hybrid traversal guidance:** The queries in this section traverse from
> `ResolvedEntityCluster` nodes using their `canonical_name` property (a text field).
> When entity-type splits exist — for example, when an entity such as "MercadoLibre"
> appears as both an `Organization` and `Person` cluster — cluster-name traversal may
> return fragmented results across multiple cluster rows.
>
> **Prefer canonical traversal ([section 7](#7-canonical-entity-traversal)) for
> post-hybrid validation and stakeholder demos.** Starting from `CanonicalEntity` nodes
> provides a single, stable entry point anchored in the curated structured catalog, and
> the `canonical → cluster → mention → claim` chain is the intended post-hybrid query
> pattern. Use the queries in this section for post-hybrid cluster-level inspection; for
> pre-hybrid traversal over resolved entities, see [section 6](#6-resolved-entity-traversal).

> **Tip:** Set parameters in Neo4j Browser before running these queries:
>
> ```cypher
> :param run_id => 'your-run-id-here'
> :param alignment_version => 'v1.0'
> ```
>
> Then add `WHERE a.run_id = $run_id AND a.alignment_version = $alignment_version` to scope
> results to a specific run; without these filters the queries may return alignments from
> multiple runs or alignment versions.

```cypher
// Clusters aligned to a canonical entity — confirm hybrid enrichment (scoped to run)
MATCH (cluster:ResolvedEntityCluster)-[a:ALIGNED_WITH]->(canonical:CanonicalEntity)
WHERE a.run_id = $run_id AND a.alignment_version = $alignment_version
RETURN cluster.canonical_name, canonical.name, a.alignment_method, a.alignment_status
ORDER BY canonical.name;
```

```cypher
// Claims reachable from a canonical entity via cluster membership (scoped to run)
MATCH (canonical:CanonicalEntity)<-[a:ALIGNED_WITH]-(cluster:ResolvedEntityCluster)<-[:MEMBER_OF]-(m:EntityMention)
WHERE toLower(canonical.name) CONTAINS 'mercadolibre'
  AND a.run_id = $run_id AND a.alignment_version = $alignment_version
MATCH (c:ExtractedClaim)-[:HAS_PARTICIPANT]->(m)
WHERE c.run_id = $run_id
RETURN c.claim_text, c.predicate, m.name AS mention, canonical.name AS canonical
ORDER BY c.claim_id;
```

```cypher
// Full cluster → mention → claim chain for Marcos Galperin (post-hybrid, scoped to run)
MATCH (canonical:CanonicalEntity)<-[a:ALIGNED_WITH]-(cluster:ResolvedEntityCluster)<-[:MEMBER_OF]-(m:EntityMention)
WHERE toLower(canonical.name) CONTAINS 'galperin'
  AND a.run_id = $run_id AND a.alignment_version = $alignment_version
MATCH (c:ExtractedClaim)-[:HAS_PARTICIPANT]->(m)
WHERE c.run_id = $run_id
RETURN canonical.name AS canonical_entity,
       cluster.canonical_name AS cluster_name,
       m.name AS mention,
       c.claim_text
ORDER BY c.claim_id;
```

---

## 5. Graph-expanded retrieval — claim participation in retrieved context (v0.3)

When using `ask --expand-graph` or `ask --cluster-aware`, the graph-expanded retrieval queries
now include a `claim_details` field for each retrieved chunk.  Unlike the flat `claims` list
(which contains only claim text), `claim_details` collects **all** `HAS_PARTICIPANT` edges as a
generic `roles` list so each claim map carries:

| Field | Description |
| --- | --- |
| `claim_text` | The full claim text |
| `roles` | List of participation entries, one per `HAS_PARTICIPANT` edge.  Each entry is `{role, mention_name, match_method}` and covers subject, object, and any future roles (agent, target, …). |
| `roles[].role` | The participation role (`'subject'`, `'object'`, or any custom value) |
| `roles[].mention_name` | Name of the resolved `EntityMention` |
| `roles[].match_method` | How the slot text was resolved (`raw_exact`, `casefold_exact`, `normalized_exact`) |

Claims with no participation edges have an empty `roles` list — **no chunk co-location fallback
is applied**.  Older data or index versions may still expose the legacy `subject_mention` /
`object_mention` dict keys; the retrieval pipeline handles both shapes transparently.
The following queries mirror what the retrieval stage now materialises for each chunk.
For the design rationale behind these semantics see
[docs/architecture/retrieval-semantics-v0.1.md](../../docs/architecture/retrieval-semantics-v0.1.md).

### 5a. Reproduce the expanded retrieval context for a single chunk

```cypher
// Simulate what --expand-graph returns for a given chunk
// (replace $chunk_id and $run_id with real values)
MATCH (c:Chunk {chunk_id: $chunk_id, run_id: $run_id})
WITH
  c,
  [(c)<-[:SUPPORTED_BY]-(claim:ExtractedClaim) WHERE claim.run_id = $run_id |
      {
        claim_text: claim.claim_text,
        roles: [(claim)-[r:HAS_PARTICIPANT]->(m:EntityMention) | {role: r.role, mention_name: m.name, match_method: r.match_method}]
      }
  ] AS claim_details,
  [(c)<-[:MENTIONED_IN]-(m:EntityMention) WHERE m.run_id = $run_id | m.name] AS mentions
RETURN c.text AS chunk_text,
       [cd IN claim_details | cd.claim_text] AS claims,
       claim_details,
       mentions;
```

### 5b. Find chunks retrieved for a specific subject entity

This query shows which chunks would surface claims where a named entity appears **as subject**
in the retrieved context — the precision improvement delivered by participation edges.

```cypher
// Chunks whose claims have Marcos Galperin as subject (via participation edges)
MATCH (claim:ExtractedClaim)-[:HAS_PARTICIPANT {role: 'subject'}]->(m:EntityMention)
WHERE toLower(m.name) CONTAINS 'galperin'
  AND claim.run_id = $run_id
MATCH (claim)-[:SUPPORTED_BY]->(chunk:Chunk)
RETURN DISTINCT chunk.chunk_id,
       chunk.chunk_index,
       claim.claim_text,
       m.name AS subject_mention
ORDER BY chunk.chunk_index;
```

### 5c. Find chunks retrieved for a specific object entity

```cypher
// Chunks whose claims have MercadoLibre as object (via participation edges)
MATCH (claim:ExtractedClaim)-[:HAS_PARTICIPANT {role: 'object'}]->(m:EntityMention)
WHERE toLower(m.name) CONTAINS 'mercadolibre'
  AND claim.run_id = $run_id
MATCH (claim)-[:SUPPORTED_BY]->(chunk:Chunk)
RETURN DISTINCT chunk.chunk_id,
       chunk.chunk_index,
       claim.claim_text,
       m.name AS object_mention
ORDER BY chunk.chunk_index;
```

### 5d. Compare explicit participation vs chunk co-location

This query illustrates the precision gain from participation edges over naive co-location:
it returns claims where the subject/object mention is confirmed via a participation edge
(explicit), alongside any additional mentions that merely co-occur in the same chunk
(implicit).  A claim that has an explicit participation edge will always be preferred for
retrieval grounding.

```cypher
// For each claim with explicit subject/object edges, show co-located mentions for comparison
MATCH (claim:ExtractedClaim)-[:SUPPORTED_BY]->(chunk:Chunk)
WHERE claim.run_id = $run_id
OPTIONAL MATCH (claim)-[sr:HAS_PARTICIPANT {role: 'subject'}]->(subj:EntityMention)
OPTIONAL MATCH (claim)-[or_:HAS_PARTICIPANT {role: 'object'}]->(obj:EntityMention)
RETURN claim.claim_text,
       subj.name  AS explicit_subject,
       sr.match_method AS subject_match,
       obj.name   AS explicit_object,
       or_.match_method AS object_match,
       [(chunk)<-[:MENTIONED_IN]-(m:EntityMention) | m.name] AS all_chunk_mentions
ORDER BY claim.claim_id
LIMIT 25;
```

**Interpretation:** `explicit_subject` / `explicit_object` are populated only when a
`HAS_PARTICIPANT {role: 'subject'}` / `{role: 'object'}` edge exists.  `all_chunk_mentions` shows
every mention in the chunk — a superset that includes mentions unrelated to this claim.
The retrieval stage uses participation edges exclusively; it does **not** fall back to
`all_chunk_mentions` for claims that lack participation edges.

---

## 5e. Retrieval-path metadata fields — observability and debugging

Every retrieved chunk's metadata now includes a `retrieval_path_diagnostics` field that
consolidates all graph-traversal provenance in a single, inspectable dict.  It is **read-only
observability**: it does not alter LLM context, citation tokens, or answer semantics.

### Per-chunk `retrieval_path_diagnostics`

Accessible via `result["retrieval_results"][i]["metadata"]["retrieval_path_diagnostics"]`
(where `result` is the dict returned by `run_retrieval_and_qa`).

| Key | Type | Description |
| --- | --- | --- |
| `has_participant_edges` | list of dicts | Per-claim role assignments. Each entry has `claim_text` (str) and `roles` (list of `{role, mention_name, match_method}`). Claims with no resolved participation edges have an empty `roles` list. |
| `canonical_via_resolves_to` | list of str | Canonical entity names reached via `EntityMention -[:RESOLVES_TO]-> CanonicalEntity`. Present when `--expand-graph` or `--cluster-aware` is active. |
| `cluster_memberships` | list of dicts | Cluster membership provenance from `MEMBER_OF` edges: `{cluster_id, cluster_name, membership_status, membership_method}`. Present when `--cluster-aware` is active. |
| `cluster_canonical_via_aligned_with` | list of dicts | Canonical entities reached transitively via `cluster -[:ALIGNED_WITH]-> CanonicalEntity`: `{canonical_name, alignment_method, alignment_status}`. Present when `--cluster-aware` is active. |

When the base retrieval query is used (no `--expand-graph`, no `--cluster-aware`), all four lists
are empty.  The key is always present so consumers can unconditionally inspect it.

### Top-level `retrieval_path_summary`

`result["retrieval_path_summary"]` contains a formatted, human-readable text summary of all
retrieved chunks and their path diagnostics. It is produced internally by the retrieval
pipeline and is useful for quick debug inspection:

```python
from demo.stages.retrieval_and_qa import run_retrieval_and_qa

result = run_retrieval_and_qa(config, run_id=run_id, question="...", cluster_aware=True)
print(result["retrieval_path_summary"])
```

Example output:
```
=== Retrieval Path Summary ===

Hit 1: chunk_id='chunk_abc'  score=0.9123
  HAS_PARTICIPANT edges (claims with participation):
    • "Marcos Galperin founded MercadoLibre." [subject='Marcos Galperin' (match: raw_exact), object='MercadoLibre' (match: casefold_exact)]
  RESOLVES_TO canonical entities: ['MercadoLibre Inc.']
  Cluster memberships (MEMBER_OF):
    • cluster='MercadoLibre'  status=accepted  method=exact
  Canonical via ALIGNED_WITH:
    • canonical='MercadoLibre Inc.'  method=embedding_similarity  status=aligned
```

`retrieval_path_summary` is always present in the result dict (empty string for dry-run and
no-question code paths).  It is purely for human inspection and must not be used for
citation or evidence evaluation.

---

## Architecture reference queries: chunk co-location

> **Note:** These are lower-level architecture queries that show how entity mentions relate to
> chunks via `MENTIONED_IN` edges.  For claim-focused analysis, prefer the participation-edge
> queries in sections 1–3 above.  Chunk co-location does not encode claim semantics; two
> mentions co-occurring in a chunk may or may not be linked by a claim.

```cypher
// All entity mentions with their source chunk (MENTIONED_IN)
MATCH (m:EntityMention)-[r:MENTIONED_IN]->(chunk:Chunk)
RETURN m.name, m.entity_type, chunk.chunk_id, chunk.run_id
LIMIT 25;
```

```cypher
// Entity mentions that co-occur in the same chunk (chunk co-location, v0.1 style)
MATCH (a:EntityMention)-[:MENTIONED_IN]->(chunk:Chunk)<-[:MENTIONED_IN]-(b:EntityMention)
WHERE a.name < b.name
RETURN a.name AS entity_a, b.name AS entity_b, count(DISTINCT chunk) AS co_occurrences
ORDER BY co_occurrences DESC
LIMIT 25;
```

```cypher
// Claims and their source chunk (via ExtractedClaim → Chunk traversal)
MATCH (c:ExtractedClaim)-[:SUPPORTED_BY]->(chunk:Chunk)
RETURN c.claim_id, c.claim_text, chunk.chunk_id, chunk.run_id
LIMIT 25;
```

```cypher
// All mentions and claims co-located in the same chunk
MATCH (m:EntityMention)-[:MENTIONED_IN]->(chunk:Chunk)<-[:SUPPORTED_BY]-(c:ExtractedClaim)
RETURN chunk.chunk_id, m.name AS mention, c.claim_text
ORDER BY chunk.chunk_id
LIMIT 25;
```

**When to use chunk co-location queries:**

- Debugging: verify that `MENTIONED_IN` edges are present for `EntityMention` nodes and that
  `SUPPORTED_BY` edges connect `ExtractedClaim` nodes to their `Chunk` nodes after `extract-claims`.
- Architecture inspection: confirm the lexical layer is intact before running downstream stages.
- Do *not* use co-location as a proxy for claim participation — use the `HAS_PARTICIPANT {role: 'subject'}` /
  `HAS_PARTICIPANT {role: 'object'}` edges instead.

---

## 6. Resolved-entity traversal (post-clustering)

These queries traverse from a `ResolvedEntityCluster` through its member `EntityMention` nodes to
the `ExtractedClaim` nodes where those mentions appear.  This cluster-based traversal is available
after `resolve-entities` and is primarily intended for `unstructured_only` / `hybrid` runs; in
`structured_anchor` mode, only *unresolved* mentions are newly clustered via `MEMBER_OF` (resolved
mentions use `RESOLVES_TO` and, in a clean DB / first-pass `structured_anchor` run, are not
reachable via this pattern). If you previously ran `unstructured_only` / `hybrid` with the same
`run_id`, some resolved mentions may still be reachable via pre-existing `MEMBER_OF` edges; to
avoid mixing behaviors, use a fresh `run_id` when switching modes.

> **Traversal path:**
> ```
> (:ResolvedEntityCluster)<-[:MEMBER_OF]-(:EntityMention)<-[:HAS_PARTICIPANT]-(:ExtractedClaim)
> ```

> **Tip:** Set a run parameter in Neo4j Browser before running these queries:
>
> ```cypher
> :param run_id => 'your-run-id-here'
> ```
>
> Then add run scoping for all relevant nodes to avoid mixing mentions across runs, for example:
> `AND cluster.run_id = $run_id`, `AND m.run_id = $run_id`, and `AND c.run_id = $run_id`, as
> shown in the `WHERE` clauses in the queries below.

### 6a. All claims for a cluster (subject or object)

```cypher
// All claims where any member of the MercadoLibre cluster appears — subject or object
// Replace 'mercadolibre' with any entity name fragment from your dataset
MATCH (cluster:ResolvedEntityCluster)<-[:MEMBER_OF]-(m:EntityMention)
WHERE toLower(cluster.canonical_name) CONTAINS 'mercadolibre'
  AND cluster.run_id = $run_id
  AND m.run_id = $run_id
MATCH (c:ExtractedClaim)-[r:HAS_PARTICIPANT]->(m)
WHERE c.run_id = $run_id
RETURN cluster.canonical_name AS cluster,
       m.name                 AS mention,
       type(r)                AS role,
       c.claim_text,
       c.predicate,
       r.match_method
ORDER BY role, c.claim_id;
```

### 6b. Claims where a cluster member appears as subject

```cypher
// Claims where any Marcos Galperin cluster member is the subject
MATCH (cluster:ResolvedEntityCluster)<-[:MEMBER_OF]-(m:EntityMention)
WHERE toLower(cluster.canonical_name) CONTAINS 'galperin'
  AND cluster.run_id = $run_id
  AND m.run_id = $run_id
MATCH (c:ExtractedClaim)-[r:HAS_PARTICIPANT {role: 'subject'}]->(m)
WHERE c.run_id = $run_id
RETURN cluster.canonical_name AS cluster,
       m.name                 AS mention,
       c.claim_text,
       c.predicate,
       c.object               AS object_slot,
       r.match_method
ORDER BY c.claim_id;
```

### 6c. Claims where a cluster member appears as object

```cypher
// Claims where any Endeavor cluster member is the object
MATCH (cluster:ResolvedEntityCluster)<-[:MEMBER_OF]-(m:EntityMention)
WHERE toLower(cluster.canonical_name) CONTAINS 'endeavor'
  AND cluster.run_id = $run_id
  AND m.run_id = $run_id
MATCH (c:ExtractedClaim)-[r:HAS_PARTICIPANT {role: 'object'}]->(m)
WHERE c.run_id = $run_id
RETURN cluster.canonical_name AS cluster,
       m.name                 AS mention,
       c.claim_text,
       c.predicate,
       c.subject              AS subject_slot,
       r.match_method
ORDER BY c.claim_id;
```

### 6d. Pairwise claim lookup — two resolved-entity clusters

```cypher
// Claims where a Galperin cluster member is subject and a MercadoLibre cluster member is object
// Pattern traversal avoids an mA × mB cross product by following claim edges in a single path
MATCH (clusterA:ResolvedEntityCluster)
WHERE toLower(clusterA.canonical_name) CONTAINS 'galperin'
  AND clusterA.run_id = $run_id
MATCH (clusterB:ResolvedEntityCluster)
WHERE toLower(clusterB.canonical_name) CONTAINS 'mercadolibre'
  AND clusterB.run_id = $run_id
WITH DISTINCT clusterA, clusterB
MATCH (clusterA)<-[:MEMBER_OF]-(mA:EntityMention)
      <-[:HAS_PARTICIPANT {role: 'subject'}]-(c:ExtractedClaim)
      -[:HAS_PARTICIPANT {role: 'object'}]->(mB:EntityMention)
      -[:MEMBER_OF]->(clusterB)
WHERE mA.run_id = $run_id
  AND mB.run_id = $run_id
  AND c.run_id  = $run_id
RETURN c.claim_id,
       c.claim_text,
       c.predicate,
       mA.name AS subject_mention,
       mB.name AS object_mention,
       clusterA.canonical_name AS subject_cluster,
       clusterB.canonical_name AS object_cluster
ORDER BY c.claim_id;
```

```cypher
// Bidirectional pairwise — either cluster in either role
// Claim-centric rewrite: start from claims and join to clusters to avoid mA × mB expansion
MATCH (c:ExtractedClaim)
WHERE c.run_id = $run_id
MATCH (c)-[:HAS_PARTICIPANT {role: 'subject'}]->(mSub:EntityMention)-[:MEMBER_OF]->(clSub:ResolvedEntityCluster)
WHERE mSub.run_id = $run_id
  AND clSub.run_id = $run_id
MATCH (c)-[:HAS_PARTICIPANT {role: 'object'}]->(mObj:EntityMention)-[:MEMBER_OF]->(clObj:ResolvedEntityCluster)
WHERE mObj.run_id = $run_id
  AND clObj.run_id = $run_id
  AND (
    (toLower(clSub.canonical_name) CONTAINS 'galperin'    AND toLower(clObj.canonical_name) CONTAINS 'mercadolibre') OR
    (toLower(clSub.canonical_name) CONTAINS 'mercadolibre' AND toLower(clObj.canonical_name) CONTAINS 'galperin')
  )
WITH DISTINCT c,
     mSub, mObj, clSub, clObj,
     CASE WHEN toLower(clSub.canonical_name) CONTAINS 'galperin' THEN 'A→B' ELSE 'B→A' END AS direction
RETURN c.claim_id,
       c.claim_text,
       c.predicate,
       mSub.name AS subject_mention,
       mObj.name AS object_mention,
       clSub.canonical_name AS subject_cluster,
       clObj.canonical_name AS object_cluster,
       direction
ORDER BY direction, c.claim_text, c.claim_id;
```

**Validation note (unstructured_only):** After running `resolve-entities` in `unstructured_only`
mode (the default), every `EntityMention` should have at least one `MEMBER_OF` edge to a
`ResolvedEntityCluster`.  The cluster-level queries above should return the same results as (or a
superset of) the raw mention-level queries in section 2, aggregating surface-form variants such
as "MercadoLibre" and "Mercado Libre" under the same cluster.

---

## 7. Canonical-entity traversal

These queries start from `CanonicalEntity` nodes.  Two traversal paths are available, depending
on the resolution mode used:

| Resolution mode | Traversal path | Edge used |
| --- | --- | --- |
| `structured_anchor` | `CanonicalEntity ← RESOLVES_TO ← EntityMention` | `RESOLVES_TO` |
| `hybrid` | `CanonicalEntity ← ALIGNED_WITH ← ResolvedEntityCluster ← MEMBER_OF ← EntityMention` | `ALIGNED_WITH` + `MEMBER_OF` |

> **Recommended for post-hybrid validation and stakeholder demos.**  Canonical traversal
> is the preferred query pattern after hybrid alignment for the following reasons:
>
> - **Deduplication at the source:** `CanonicalEntity` nodes are written by
>   `ingest-structured` from a curated catalog and are deduplicated by design.  A
>   cluster-name traversal that matches on the text field `canonical_name` can return
>   multiple rows when entity-type splits produce more than one `ResolvedEntityCluster`
>   for the same real-world entity (e.g., "MercadoLibre" appearing as both
>   `Organization` and `Person` clusters).  Starting from `CanonicalEntity` collapses
>   those splits into a single, authoritative entry point.
> - **Full resolution model in one traversal:** The
>   `canonical → cluster → mention → claim` path exposes every layer of the hybrid
>   resolution model — catalog identity, surface-form grouping, and claim participation
>   — in a single chain.  This makes it the most informative and self-documenting path
>   for demos and evaluation.
> - **Stable across alignment reruns:** `CanonicalEntity` nodes are written once by
>   `ingest-structured` and remain constant.  Only `ALIGNED_WITH` edges are updated
>   when `resolve-entities --resolution-mode hybrid` is rerun, so canonical-anchored
>   queries continue to work correctly after incremental alignment updates.
>
> Use [section 4](#4-cluster-aware-entity-traversal-post-hybrid) for post-hybrid
> cluster-level inspection, [section 6](#6-cluster-aware-entity-traversal-pre-hybrid) for
> pre-hybrid cluster traversal, and [section 12d](#12d-hybrid-alignment-coverage) for alignment coverage diagnostics.

> **Tip:** Set parameters in Neo4j Browser before running these queries:
>
> ```cypher
> :param run_id           => 'your-run-id-here'
> :param alignment_version => 'v1.0'
> ```

### 7a. Claims via RESOLVES_TO (structured_anchor mode)

```cypher
// All claims where any mention resolving directly to MercadoLibre appears — subject or object
MATCH (canonical:CanonicalEntity)<-[:RESOLVES_TO]-(m:EntityMention)
WHERE toLower(canonical.name) CONTAINS 'mercadolibre'
  AND m.run_id = $run_id
MATCH (c:ExtractedClaim)-[r:HAS_PARTICIPANT]->(m)
WHERE c.run_id = $run_id
RETURN canonical.name AS canonical_entity,
       m.name         AS mention,
       type(r)        AS role,
       c.claim_text,
       c.predicate,
       r.match_method
ORDER BY role, c.claim_id;
```

```cypher
// Claims where MercadoLibre (canonical) appears as subject — structured_anchor mode
MATCH (canonical:CanonicalEntity)<-[:RESOLVES_TO]-(m:EntityMention)
WHERE toLower(canonical.name) CONTAINS 'mercadolibre'
  AND m.run_id = $run_id
MATCH (c:ExtractedClaim)-[r:HAS_PARTICIPANT {role: 'subject'}]->(m)
WHERE c.run_id = $run_id
RETURN canonical.name AS canonical_entity,
       m.name         AS mention,
       c.claim_text,
       c.predicate,
       c.object       AS object_slot,
       r.match_method
ORDER BY c.claim_id;
```

### 7b. Claims via ALIGNED_WITH (hybrid mode)

```cypher
// All claims reachable from MercadoLibre canonical entity via hybrid alignment
MATCH (canonical:CanonicalEntity)<-[a:ALIGNED_WITH]-(cluster:ResolvedEntityCluster)<-[:MEMBER_OF]-(m:EntityMention)
WHERE toLower(canonical.name) CONTAINS 'mercadolibre'
  AND a.run_id = $run_id AND a.alignment_version = $alignment_version
  AND m.run_id = $run_id
MATCH (c:ExtractedClaim)-[r:HAS_PARTICIPANT]->(m)
WHERE c.run_id = $run_id
RETURN canonical.name        AS canonical_entity,
       cluster.canonical_name AS cluster,
       m.name                 AS mention,
       type(r)                AS role,
       c.claim_text,
       c.predicate,
       r.match_method
ORDER BY role, c.claim_id;
```

```cypher
// Full chain — Marcos Galperin canonical → cluster → mentions → claims as subject (hybrid mode)
MATCH (canonical:CanonicalEntity)<-[a:ALIGNED_WITH]-(cluster:ResolvedEntityCluster)<-[:MEMBER_OF]-(m:EntityMention)
WHERE toLower(canonical.name) CONTAINS 'galperin'
  AND a.run_id = $run_id AND a.alignment_version = $alignment_version
  AND m.run_id = $run_id
MATCH (c:ExtractedClaim)-[r:HAS_PARTICIPANT {role: 'subject'}]->(m)
WHERE c.run_id = $run_id
RETURN canonical.name        AS canonical_entity,
       cluster.canonical_name AS cluster,
       m.name                 AS mention,
       c.claim_text,
       c.predicate,
       c.object               AS object_slot,
       r.match_method
ORDER BY c.claim_id;
```

### 7c. Pairwise claim lookup — two canonical entities (hybrid mode)

```cypher
// Claims where Marcos Galperin (canonical) is subject and MercadoLibre (canonical) is object
// Single-path traversal avoids an mA × mB cross product
MATCH (canonA:CanonicalEntity)<-[aA:ALIGNED_WITH]-(clA:ResolvedEntityCluster)<-[:MEMBER_OF]-
      (mA:EntityMention)<-[:HAS_PARTICIPANT {role: 'subject'}]-
      (c:ExtractedClaim)-[:HAS_PARTICIPANT {role: 'object'}]->
      (mB:EntityMention)-[:MEMBER_OF]->
      (clB:ResolvedEntityCluster)-[aB:ALIGNED_WITH]->(canonB:CanonicalEntity)
WHERE toLower(canonA.name) CONTAINS 'galperin'
  AND toLower(canonB.name) CONTAINS 'mercadolibre'
  AND aA.run_id = $run_id AND aA.alignment_version = $alignment_version
  AND aB.run_id = $run_id AND aB.alignment_version = $alignment_version
  AND mA.run_id = $run_id
  AND mB.run_id = $run_id
  AND c.run_id  = $run_id
WITH DISTINCT c, canonA, canonB, mA, mB
RETURN c.claim_id,
       c.claim_text,
       c.predicate,
       mA.name     AS subject_mention,
       mB.name     AS object_mention,
       canonA.name AS subject_canonical,
       canonB.name AS object_canonical
ORDER BY c.claim_id;
```

```cypher
// Bidirectional pairwise — either canonical entity in either role (hybrid mode)
// Claim-centric rewrite: start from claims to avoid mA × mB expansion
MATCH (c:ExtractedClaim)
WHERE c.run_id = $run_id
MATCH (c)-[:HAS_PARTICIPANT {role: 'subject'}]->(mSub:EntityMention)
WHERE mSub.run_id = $run_id
MATCH (c)-[:HAS_PARTICIPANT {role: 'object'}]->(mObj:EntityMention)
WHERE mObj.run_id = $run_id
MATCH (mSub)-[:MEMBER_OF]->(clSub:ResolvedEntityCluster)-[aSub:ALIGNED_WITH]->(canonSub:CanonicalEntity)
WHERE aSub.run_id = $run_id
  AND aSub.alignment_version = $alignment_version
MATCH (mObj)-[:MEMBER_OF]->(clObj:ResolvedEntityCluster)-[aObj:ALIGNED_WITH]->(canonObj:CanonicalEntity)
WHERE aObj.run_id = $run_id
  AND aObj.alignment_version = $alignment_version
  AND (
    (toLower(canonSub.name) CONTAINS 'galperin'    AND toLower(canonObj.name) CONTAINS 'mercadolibre') OR
    (toLower(canonSub.name) CONTAINS 'mercadolibre' AND toLower(canonObj.name) CONTAINS 'galperin')
  )
WITH DISTINCT c, mSub, mObj, canonSub, canonObj,
     CASE WHEN toLower(canonSub.name) CONTAINS 'galperin' THEN 'A→B' ELSE 'B→A' END AS direction
RETURN c.claim_id    AS claim_id,
       c.claim_text  AS claim_text,
       c.predicate   AS predicate,
       mSub.name     AS subject,
       mObj.name     AS object,
       direction
ORDER BY direction, claim_text, claim_id;
```

**Validation note (hybrid):** After running `resolve-entities --resolution-mode hybrid` and
`ingest-structured`, the queries above should return at least one row for Galperin and MercadoLibre
when those names appear in the structured CSV fixtures.  If the queries return no results, verify:

1. `ingest-structured` completed successfully and `CanonicalEntity` nodes exist (quick check:
   `MATCH (n:CanonicalEntity) RETURN count(n)`).
2. `resolve-entities --resolution-mode hybrid` completed with `aligned_clusters > 0` in the
   entity resolution manifest.
3. The `$run_id` and `$alignment_version` parameter values match those in the entity resolution
   summary artifact.

---

## 8. Aggregate analytics

These queries answer *"How many claims involve each entity?"* — useful for identifying the most
claim-active entities and exploring the overall claim landscape.

### 8a. Claim count per ResolvedEntityCluster

```cypher
// Clusters ranked by number of associated claims (all roles) — scoped to a single run
MATCH (cluster:ResolvedEntityCluster)<-[:MEMBER_OF]-(m:EntityMention)
WHERE cluster.run_id = $run_id
  AND m.run_id = $run_id
MATCH (c:ExtractedClaim)-[:HAS_PARTICIPANT]->(m)
WHERE c.run_id = $run_id
RETURN cluster.canonical_name AS cluster,
       cluster.entity_type,
       count(DISTINCT c) AS claim_count,
       count(DISTINCT m) AS participating_mention_count
ORDER BY claim_count DESC
LIMIT 20;
```

```cypher
// Claim count per cluster, broken down by subject vs. object role
MATCH (cluster:ResolvedEntityCluster)<-[:MEMBER_OF]-(m:EntityMention)
WHERE cluster.run_id = $run_id
  AND m.run_id = $run_id
MATCH (c:ExtractedClaim)-[r:HAS_PARTICIPANT]->(m)
WHERE c.run_id = $run_id
RETURN cluster.canonical_name AS cluster,
       type(r)                AS role,
       count(DISTINCT c)      AS claim_count
ORDER BY cluster, role;
```

### 8b. Claim count per CanonicalEntity (hybrid mode)

```cypher
// Canonical entities ranked by number of associated claims via ALIGNED_WITH (hybrid mode)
MATCH (canonical:CanonicalEntity)<-[a:ALIGNED_WITH]-(cluster:ResolvedEntityCluster)<-[:MEMBER_OF]-(m:EntityMention)
WHERE a.run_id = $run_id
  AND a.alignment_version = $alignment_version
  AND m.run_id = $run_id
MATCH (c:ExtractedClaim)-[:HAS_PARTICIPANT]->(m)
WHERE c.run_id = $run_id
RETURN canonical.name       AS canonical_entity,
       canonical.entity_id,
       count(DISTINCT c)    AS claim_count,
       count(DISTINCT m)    AS participating_mention_count,
       count(DISTINCT cluster) AS cluster_count
ORDER BY claim_count DESC
LIMIT 20;
```

### 8c. Cluster-to-claim coverage summary

```cypher
// How many clusters have at least one associated claim? How many are 'dark' (no claims)?
MATCH (cluster:ResolvedEntityCluster)
WHERE cluster.run_id = $run_id
OPTIONAL MATCH (cluster)<-[:MEMBER_OF]-(m:EntityMention)<-[:HAS_PARTICIPANT]-(c:ExtractedClaim)
WHERE m.run_id = $run_id AND c.run_id = $run_id
WITH cluster, count(DISTINCT c) AS claim_count
RETURN sum(CASE WHEN claim_count > 0 THEN 1 ELSE 0 END) AS clusters_with_claims,
       sum(CASE WHEN claim_count = 0 THEN 1 ELSE 0 END) AS clusters_without_claims,
       count(cluster)                                    AS total_clusters;
```

**Interpretation:** `clusters_without_claims` ("dark" clusters) are entity clusters for which no
participation edges were resolved — either because the entity mentions appear in the graph but were
never slot-matched to a claim, or because the claim-participation stage did not find a unique match
for those mentions.  Dark clusters are not an error; they represent entities extracted from the
document that happen not to appear in any claim's subject or object slots.

---

## 9. Demo scenario — entity-centric exploration

This scenario demonstrates end-to-end exploration starting from a resolved entity and traversing
to all associated claims.  It applies after completing Steps 2–4 (unstructured-only pass) or
Steps 2–4b (with hybrid enrichment) in the demo workflow.

> **Prerequisites:** complete the unstructured-only pass
> (`ingest-pdf` → `extract-claims` → `resolve-entities`) and record the `UNSTRUCTURED_RUN_ID`.

**Set your run parameter in Neo4j Browser once, then run the steps in order:**

```cypher
:param run_id           => '<your-UNSTRUCTURED_RUN_ID-here>'
:param alignment_version => 'v1.0'
```

### Step 1 — Confirm clusters exist for your target entity

```cypher
// Inspect clusters for 'mercadolibre' — confirms entity resolution ran successfully
MATCH (cluster:ResolvedEntityCluster)
WHERE toLower(cluster.canonical_name) CONTAINS 'mercadolibre'
  AND cluster.run_id = $run_id
RETURN cluster.cluster_id, cluster.canonical_name, cluster.entity_type, cluster.normalized_text;
```

**Expected result:** One or more `ResolvedEntityCluster` rows for 'mercadolibre'.
If no rows are returned, verify that `resolve-entities` completed with `mentions_clustered > 0` in
the entity resolution summary.

### Step 2 — List all member mentions for the cluster

```cypher
// All EntityMention nodes belonging to the MercadoLibre cluster
MATCH (cluster:ResolvedEntityCluster)<-[r:MEMBER_OF]-(m:EntityMention)
WHERE toLower(cluster.canonical_name) CONTAINS 'mercadolibre'
  AND cluster.run_id = $run_id
  AND m.run_id = $run_id
RETURN m.name          AS mention_name,
       m.entity_type,
       r.method        AS resolution_method,
       r.score
ORDER BY r.method, m.name;
```

**Expected result:** All surface-form variants of "MercadoLibre" that appeared in the document
(e.g., "MercadoLibre", "Mercado Libre", "ML") are listed as members of the same cluster.

### Step 3 — Traverse to all claims for the cluster

```cypher
// All claims where any MercadoLibre cluster member appears — subject or object
MATCH (cluster:ResolvedEntityCluster)<-[:MEMBER_OF]-(m:EntityMention)
WHERE toLower(cluster.canonical_name) CONTAINS 'mercadolibre'
  AND cluster.run_id = $run_id
  AND m.run_id = $run_id
MATCH (c:ExtractedClaim)-[r:HAS_PARTICIPANT]->(m)
WHERE c.run_id = $run_id
RETURN cluster.canonical_name AS cluster,
       m.name                 AS mention,
       type(r)                AS role,
       c.claim_text,
       c.predicate,
       r.match_method
ORDER BY role, c.claim_id;
```

**Expected result:** Claims where MercadoLibre (in any surface form) appears as either the subject
or object of an extracted claim from the source document.

### Step 4 — Find which entities make claims about MercadoLibre

```cypher
// Which entities appear as subject when MercadoLibre is the object?
MATCH (cluster:ResolvedEntityCluster)<-[:MEMBER_OF]-(mObj:EntityMention)
WHERE toLower(cluster.canonical_name) CONTAINS 'mercadolibre'
  AND cluster.run_id = $run_id
  AND mObj.run_id = $run_id
MATCH (c:ExtractedClaim)-[:HAS_PARTICIPANT {role: 'object'}]->(mObj)
WHERE c.run_id = $run_id
MATCH (c)-[:HAS_PARTICIPANT {role: 'subject'}]->(mSubj:EntityMention)
RETURN DISTINCT mSubj.name AS subject_entity,
                count(c)   AS claim_count
ORDER BY claim_count DESC;
```

### Step 5 — Extend to canonical entity (post-hybrid only)

After running `ingest-structured` and `resolve-entities --resolution-mode hybrid`:

```cypher
// Confirm ALIGNED_WITH edges exist for MercadoLibre
MATCH (canonical:CanonicalEntity)<-[a:ALIGNED_WITH]-(cluster:ResolvedEntityCluster)<-[:MEMBER_OF]-(m:EntityMention)
WHERE toLower(canonical.name) CONTAINS 'mercadolibre'
  AND a.run_id = $run_id AND a.alignment_version = $alignment_version
  AND m.run_id = $run_id
RETURN canonical.name        AS canonical_entity,
       canonical.entity_id,
       cluster.canonical_name AS cluster,
       count(DISTINCT m)      AS mention_count,
       a.alignment_method,
       a.alignment_score
ORDER BY cluster;
```

```cypher
// Full canonical → cluster → mention → claim chain for MercadoLibre (hybrid mode)
MATCH (canonical:CanonicalEntity)<-[a:ALIGNED_WITH]-(cluster:ResolvedEntityCluster)<-[:MEMBER_OF]-(m:EntityMention)
WHERE toLower(canonical.name) CONTAINS 'mercadolibre'
  AND a.run_id = $run_id AND a.alignment_version = $alignment_version
  AND m.run_id = $run_id
MATCH (c:ExtractedClaim)-[r:HAS_PARTICIPANT]->(m)
WHERE c.run_id = $run_id
RETURN canonical.name        AS canonical_entity,
       cluster.canonical_name AS cluster,
       m.name                 AS mention,
       type(r)                AS role,
       c.claim_text,
       c.predicate,
       r.match_method
ORDER BY role, c.claim_id;
```

**Expected result:** Same claims as Step 3, now with a `canonical_entity` column confirming that
the traversal bridged from the curated structured catalog to the extracted claims.

### Validation checklist

| Check | Expected |
| --- | --- |
| Step 1 returns rows | ✅ Entity resolution ran and clusters exist |
| Step 2 shows multiple surface forms | ✅ Normalization/fuzzy matching collapsed variants |
| Step 3 returns claims | ✅ Participation edges exist for this entity's mentions |
| Step 5 `ALIGNED_WITH` query returns rows | ✅ Hybrid alignment linked the cluster to the curated entity |
| Step 5 full chain returns same claims as Step 3 | ✅ Canonical traversal is consistent with cluster traversal |

---

## 10. Stakeholder demo — canonical traversal query flow (hybrid mode)

This section provides a recommended, end-to-end query flow for stakeholder demos and
post-hybrid validation sessions.  All queries start from `CanonicalEntity` nodes to
avoid fragmented results from raw cluster-name views and to present the full resolution
model — canonical identity → cluster grouping → surface-form mention → claim —
in a single, legible chain.

> **Prerequisites:** complete the full hybrid pipeline pass
> (`ingest-pdf` → `extract-claims` → `resolve-entities` → `ingest-structured` →
> `resolve-entities --resolution-mode hybrid`) and record `UNSTRUCTURED_RUN_ID`.
>
> Set your run parameters once in Neo4j Browser before running the steps below:
>
> ```cypher
> :param run_id           => '<your-UNSTRUCTURED_RUN_ID-here>'
> :param alignment_version => 'v1.0'
> ```

### Step 1 — Confirm canonical entities exist and are aligned

```cypher
// Canonical entities with at least one aligned cluster in this run
// (confirms ingest-structured + hybrid alignment both ran successfully)
MATCH (canonical:CanonicalEntity)<-[a:ALIGNED_WITH]-(cluster:ResolvedEntityCluster)
WHERE a.run_id = $run_id
  AND a.alignment_version = $alignment_version
  AND cluster.run_id = $run_id
RETURN canonical.name        AS canonical_entity,
       canonical.entity_type AS entity_type,
       count(DISTINCT cluster) AS aligned_cluster_count,
       collect(DISTINCT a.alignment_method)[0..3] AS sample_methods
ORDER BY aligned_cluster_count DESC;
```

**Expected result:** One or more rows showing canonical entity names matched in the
structured catalog and their aligned cluster counts.  `sample_methods` lists the
alignment strategies used (e.g., `label_exact`, `alias_exact`).  A zero-row result
means either `ingest-structured` did not complete, or
`resolve-entities --resolution-mode hybrid` reported `aligned_clusters = 0`.

### Step 2 — Traverse the full canonical → cluster → mention → claim chain

```cypher
// All claims reachable from MercadoLibre's canonical entity via hybrid path
// Demonstrates the complete resolution model: canonical → cluster → mention → claim
MATCH (canonical:CanonicalEntity)<-[a:ALIGNED_WITH]-(cluster:ResolvedEntityCluster)<-[:MEMBER_OF]-(m:EntityMention)
WHERE toLower(canonical.name) CONTAINS 'mercadolibre'
  AND a.run_id = $run_id AND a.alignment_version = $alignment_version
  AND m.run_id = $run_id
  AND cluster.run_id = $run_id
MATCH (c:ExtractedClaim)-[r:HAS_PARTICIPANT]->(m)
WHERE c.run_id = $run_id
RETURN canonical.name        AS canonical_entity,
       cluster.canonical_name AS cluster,
       m.name                 AS mention,
       r.role                 AS role,
       c.claim_text,
       c.predicate,
       r.match_method
ORDER BY r.role, c.claim_id;
```

**Talking point:** Each row exposes all three resolution layers — the curated canonical
name, the normalized cluster grouping, and the raw surface form from the document —
making it straightforward to trace every claim back to its extraction source.

### Step 3 — Pairwise canonical claim lookup (subject ↔ object)

```cypher
// Claims where Marcos Galperin (canonical) is subject and MercadoLibre (canonical) is object
MATCH (canonA:CanonicalEntity)<-[aA:ALIGNED_WITH]-(clA:ResolvedEntityCluster)<-[:MEMBER_OF]-
      (mA:EntityMention)<-[:HAS_PARTICIPANT {role: 'subject'}]-
      (c:ExtractedClaim)-[:HAS_PARTICIPANT {role: 'object'}]->
      (mB:EntityMention)-[:MEMBER_OF]->
      (clB:ResolvedEntityCluster)-[aB:ALIGNED_WITH]->(canonB:CanonicalEntity)
WHERE toLower(canonA.name) CONTAINS 'galperin'
  AND toLower(canonB.name) CONTAINS 'mercadolibre'
  AND aA.run_id = $run_id AND aA.alignment_version = $alignment_version
  AND aB.run_id = $run_id AND aB.alignment_version = $alignment_version
  AND mA.run_id = $run_id
  AND mB.run_id = $run_id
  AND c.run_id  = $run_id
  AND clA.run_id = $run_id
  AND clB.run_id = $run_id
WITH DISTINCT c, canonA, canonB, mA, mB
RETURN c.claim_id,
       c.claim_text,
       c.predicate,
       mA.name     AS subject_mention,
       mB.name     AS object_mention,
       canonA.name AS subject_canonical,
       canonB.name AS object_canonical
ORDER BY c.claim_id;
```

**Talking point:** Both entity slots are resolved to their curated canonical identities,
so this query surfaces claims regardless of how each entity was spelled or abbreviated
in the source document.

### Step 4 — Coverage summary: how many claims does each canonical entity appear in?

```cypher
// Canonical entities ranked by reachable claim count via hybrid path
MATCH (canonical:CanonicalEntity)<-[a:ALIGNED_WITH]-(cluster:ResolvedEntityCluster)<-[:MEMBER_OF]-(m:EntityMention)
WHERE a.run_id = $run_id
  AND a.alignment_version = $alignment_version
  AND cluster.run_id = $run_id
  AND m.run_id = $run_id
OPTIONAL MATCH (c:ExtractedClaim {run_id: $run_id})-[:HAS_PARTICIPANT]->(m)
WITH canonical, count(DISTINCT m) AS mention_count, count(DISTINCT c) AS claim_count
RETURN canonical.name        AS canonical_entity,
       canonical.entity_type AS entity_type,
       mention_count,
       claim_count,
       CASE WHEN claim_count = 0 THEN 'dark' ELSE 'active' END AS status
ORDER BY claim_count DESC
LIMIT 20;
```

**Talking point:** `status = 'active'` entities have at least one claim traceable to
the curated catalog.  `status = 'dark'` entities are aligned to a cluster but none of
those cluster members appear as participants in any extracted claim — a useful signal
for coverage gaps (e.g., entities present in the structured catalog that did not
appear in any claim's subject or object slot in this document).

### Stakeholder demo checklist

| Step | Expected | What it confirms |
| --- | --- | --- |
| Step 1 returns rows | ✅ At least one `ALIGNED_WITH` edge for this run | `ingest-structured` + hybrid alignment ran successfully |
| Step 2 returns claims with `canonical_entity` populated | ✅ Full canonical → claim chain intact | Claims are reachable via the hybrid traversal path |
| Step 3 returns at least one row for Galperin ↔ MercadoLibre | ✅ Pairwise canonical claim resolved | Both subject and object slots resolved to canonical entities |
| Step 4 shows `active` entries for key entities | ✅ Canonical entities contribute to retrieval | Hybrid enrichment is surfaced in claim analytics |

---

## 11. Derived edge analysis — materializing claim→cluster and claim→canonical edges

This section analyses whether derived shortcut edges from `ExtractedClaim` directly to
`ResolvedEntityCluster` or `CanonicalEntity` would improve query ergonomics or performance, and
documents the current recommendation.

### Current traversal depth

| Goal | Cypher path | Hops |
| --- | --- | --- |
| Cluster → associated claims | `(cluster)←[:MEMBER_OF]←(m)←[:HAS_SUBJECT/OBJECT_MENTION]←(claim)` | 2 |
| Canonical → claims (hybrid) | `(canonical)←[:ALIGNED_WITH]←(cluster)←[:MEMBER_OF]←(m)←[:HAS_SUBJECT/OBJECT_MENTION]←(claim)` | 3 |
| Canonical → claims (structured_anchor) | `(canonical)←[:RESOLVES_TO]←(m)←[:HAS_SUBJECT/OBJECT_MENTION]←(claim)` | 2 |

### What materialized edges would look like

Two derived relationship types could be pre-computed:

- **`CLAIM_INVOLVES_CLUSTER`** (`ExtractedClaim → ResolvedEntityCluster`) — shortens
  cluster → claims lookups to a single hop.
- **`CLAIM_INVOLVES_CANONICAL`** (`ExtractedClaim → CanonicalEntity`) — shortens
  canonical → claims lookups to a single hop.

### Analysis

**Arguments in favour of materialization:**
- Reduces traversal cost for high-frequency analytics at large data volumes (e.g., computing
  per-entity claim counts across millions of claims).
- Simplifies Cypher for downstream consumers — callers no longer need to understand the full
  multi-hop resolution model.

**Arguments against materialization (current recommendation):**
- The 2–3 hop traversal is typically manageable when standard Neo4j indexes on `run_id`,
  `cluster_id`, and `entity_id` are created. For the data volumes targeted by v0.1, and with
  these indexes in place (recommended for interactive analytics workloads), these queries run
  well within interactive latency budgets.
- Materialized edges duplicate information already encoded in participation edges
  (`HAS_PARTICIPANT {role: 'subject'}` / `HAS_PARTICIPANT {role: 'object'}`) and resolution edges (`MEMBER_OF` /
  `ALIGNED_WITH`), increasing write cost and introducing a consistency surface.
- Resolution results can change when `resolve-entities` is re-run (updated `MEMBER_OF` and
  `ALIGNED_WITH` edges).  Materialized edges would need to be explicitly invalidated and rebuilt
  on every re-resolution, adding operational complexity and a potential for stale data.
- The existing graph model already fully supports all analytical and audit use cases without
  derived edges.

### Recommendation

**Do not materialize `CLAIM_INVOLVES_CLUSTER` or `CLAIM_INVOLVES_CANONICAL` edges in v0.1.**

The existing 2–3 hop traversal via `MEMBER_OF` and `ALIGNED_WITH` is the correct and sufficient
approach.  If future benchmarking at production-scale data volumes demonstrates that analytics
queries are a performance bottleneck, materialized edges should be considered as an explicit
optimization — not pre-emptively.  Any such decision should be documented as a schema migration
with explicit versioning and invalidation semantics.

If the concern is query ergonomics rather than performance, consider wrapping the traversal in a
named Neo4j stored procedure or an APOC virtual graph shortcut rather than adding a redundant
edge type to the core schema.

---

## 12. Direct-DB diagnostics — participation coverage, cluster fragmentation, and hybrid alignment

These queries are designed for direct database health checks. Run them after completing a full
pipeline pass to validate retrieval-graph integrity before running live queries. Most queries are
self-contained and can be run as-is; some are scoped variants that accept parameters (for example,
a specific `$run_id`). Results are returned as either single aggregate values or compact multi-row
tables that can be inspected at a glance.

> **When to use this section:** after any pipeline run, when troubleshooting low retrieval
> quality, or as a regression check when schema or pipeline changes are deployed.

---

### 12a. Participation coverage

**Role distribution** — confirms that `HAS_PARTICIPANT` edges were written for every expected
argument role and reveals any role that is under-populated.

```cypher
// Edge counts by participation role (all runs)
MATCH ()-[r:HAS_PARTICIPANT]->()
RETURN r.role AS role, count(*) AS total
ORDER BY total DESC;
```

**Interpretation:** Every role present in the extraction model (`subject`, `object`, and any
additional roles) should appear in the result. A role with zero rows or a count far below the
others indicates that the claim-participation stage failed to resolve matches for that slot.

---

**Claim edge-coverage distribution** — shows how many `HAS_PARTICIPANT` edges each
`ExtractedClaim` received, revealing claims that were left with no participation links.

```cypher
// Distribution of HAS_PARTICIPANT edge counts per ExtractedClaim (all runs)
MATCH (c:ExtractedClaim)
OPTIONAL MATCH (c)-[r:HAS_PARTICIPANT]->(:EntityMention)
WITH c, count(r) AS participant_edges
RETURN participant_edges, count(*) AS claim_count
ORDER BY participant_edges;
```

**Interpretation:** A large `claim_count` for `participant_edges = 0` means many claims were not
linked to any entity mention. This can occur when:

- The extraction LLM left subject/object slots blank.
- The mention text did not match any `EntityMention` in the same chunk (no exact or
  normalized match was found).
- The claim-participation stage was not run for those claims.

Claims with `participant_edges >= 1` are retrievable via entity-centric traversal.

---

**Per-run participation summary** — scoped breakdown to compare runs side-by-side.

```cypher
// Total HAS_PARTICIPANT edges per run_id
MATCH ()-[r:HAS_PARTICIPANT]->()
RETURN r.run_id AS run_id, r.role AS role, count(*) AS total
ORDER BY run_id, role;
```

---

### 12b. Mention clustering

**Unclustered mention rate / missing MEMBER_OF edges** — `EntityMention` nodes that have no
`MEMBER_OF` edge to any `ResolvedEntityCluster`. Note that in `structured_anchor` mode, mentions
resolved via a `RESOLVES_TO` edge intentionally have no `MEMBER_OF` edge, so an
`is_clustered = false` result is not necessarily pathological — it depends on the resolution mode
used. These mentions are still reachable by claim-based traversal; they are only invisible to
cluster-level and canonical-level analytics.

```cypher
// Mentions with and without a MEMBER_OF edge (all runs)
MATCH (m:EntityMention)
OPTIONAL MATCH (m)-[:MEMBER_OF]->(cluster:ResolvedEntityCluster)
WITH m, count(cluster) > 0 AS is_clustered
RETURN is_clustered, count(DISTINCT m) AS mention_count
ORDER BY is_clustered DESC;
```

**Interpretation:** `is_clustered = false` counts are expected when `structured_anchor` mode was
used (mentions anchor to canonical entities via `RESOLVES_TO` rather than cluster membership). If
the resolution mode was `hybrid` or `unstructured_only`, a large unclustered count may indicate
that `resolve-entities` did not run to completion — verify that its manifest reports
`mentions_clustered > 0`.

---

**Cluster size distribution** — shows the spread of how many mentions each cluster contains,
which informs whether normalization and fuzzy-matching are collapsing surface variants as expected.

```cypher
// Number of member EntityMention nodes per ResolvedEntityCluster (all runs)
MATCH (cluster:ResolvedEntityCluster)<-[:MEMBER_OF]-(m:EntityMention)
WITH cluster, count(m) AS member_count
RETURN member_count, count(cluster) AS cluster_count
ORDER BY member_count;
```

**Interpretation:** Clusters with `member_count = 1` are singletons — the entity appeared in
only one surface form across the corpus. A healthy run should show some multi-member clusters
(collapsed variants). A distribution that is *entirely* singletons may indicate that
normalization / fuzzy-matching thresholds are too strict or that the corpus is small.

---

### 12c. Cluster fragmentation by type

**Entity-type distribution within clusters** — a cluster should ideally contain mentions of
a single entity type. Clusters with mixed types suggest over-aggressive merging.

```cypher
// For each cluster, count how many distinct (normalized) entity_type values its member mentions have
MATCH (cluster:ResolvedEntityCluster)<-[:MEMBER_OF]-(m:EntityMention)
WITH cluster,
     CASE
       WHEN m.entity_type IS NULL OR trim(m.entity_type) = '' THEN 'UNKNOWN'
       ELSE
         CASE toUpper(trim(m.entity_type))
           WHEN 'PERSON'   THEN 'Person'
           WHEN 'ORG'      THEN 'Organization'
           WHEN 'COMPANY'  THEN 'Organization'
           ELSE trim(m.entity_type)
         END
     END AS normalized_type
WITH cluster,
     count(DISTINCT normalized_type) AS type_count
RETURN type_count             AS distinct_types_in_cluster,
       count(cluster)         AS cluster_count
ORDER BY type_count;
```

**Interpretation:** `distinct_types_in_cluster = 1` is the expected healthy state (all mentions
in a cluster share the same entity type). Values greater than 1 indicate that the cluster
contains mentions of different entity types and may represent a resolution error.

---

**Fragmented clusters — detail view** — lists every cluster that contains more than one distinct
entity type, for manual inspection.

```cypher
// Clusters whose member mentions span more than one entity_type (all runs)
MATCH (cluster:ResolvedEntityCluster)<-[:MEMBER_OF]-(m:EntityMention)
WITH cluster,
     collect(DISTINCT coalesce(nullif(trim(toUpper(m.entity_type)), ''), 'UNKNOWN')) AS types,
     count(DISTINCT coalesce(nullif(trim(toUpper(m.entity_type)), ''), 'UNKNOWN'))   AS type_count
WHERE type_count > 1
RETURN cluster.run_id          AS run_id,
       cluster.cluster_id      AS cluster_id,
       cluster.canonical_name  AS canonical_name,
       cluster.entity_type     AS cluster_entity_type,
       types                   AS member_entity_types,
       type_count
ORDER BY type_count DESC, cluster.canonical_name
LIMIT 50;
```

---

**Cluster entity-type summary** — aggregate count of clusters per declared `entity_type` on the
cluster node, confirming type balance across the resolved graph.

```cypher
// How many ResolvedEntityCluster nodes exist per entity_type (all runs)
MATCH (cluster:ResolvedEntityCluster)
RETURN cluster.entity_type AS entity_type, count(*) AS cluster_count
ORDER BY cluster_count DESC;
```

---

### 12d. Hybrid alignment coverage

**Alignment counts** — counts of `ResolvedEntityCluster` nodes that have or have not been linked to a
`CanonicalEntity` via an `ALIGNED_WITH` edge. Only applicable after running
`resolve-entities --resolution-mode hybrid`.

```cypher
// Parameter (set before running the query)
// :param alignment_version => 'v1.0'

// Clusters with and without ALIGNED_WITH edges for a given alignment_version
MATCH (cluster:ResolvedEntityCluster)
OPTIONAL MATCH (cluster)-[a:ALIGNED_WITH]->(:CanonicalEntity)
  WHERE a.run_id = cluster.run_id
    AND a.alignment_version = $alignment_version
WITH cluster, count(a) > 0 AS is_aligned
RETURN is_aligned, count(*) AS cluster_count
ORDER BY is_aligned DESC;
```

**Interpretation:** `is_aligned = false` clusters are those for which no matching
`CanonicalEntity` was found in the structured catalog. This is expected for entities that appear
only in the unstructured source and have no structured counterpart. A high unaligned rate when
canonical counterparts *are* expected may indicate a threshold issue or a data loading problem
with `ingest-structured`.

---

**Per-canonical alignment summary** — shows how many clusters and mentions are aligned to each
`CanonicalEntity`, useful for confirming that the structured catalog is contributing to retrieval.

```cypher
// Canonical entities ranked by number of aligned clusters and bridged mentions
// (scoped to $run_id and $alignment_version)
MATCH (canonical:CanonicalEntity)<-[a:ALIGNED_WITH]-(cluster:ResolvedEntityCluster)<-[:MEMBER_OF]-(m:EntityMention)
WHERE a.run_id = $run_id
  AND a.alignment_version = $alignment_version
  AND cluster.run_id = $run_id
  AND m.run_id = $run_id
RETURN canonical.name              AS canonical_entity,
       canonical.entity_id         AS entity_id,
       canonical.entity_type       AS entity_type,
       count(DISTINCT cluster)     AS aligned_cluster_count,
       count(DISTINCT m)           AS bridged_mention_count,
       collect(DISTINCT a.alignment_method)[0..5] AS sample_methods
ORDER BY aligned_cluster_count DESC
LIMIT 20;
```

---

**Unaligned cluster detail** — lists clusters that have no `ALIGNED_WITH` edge for the current
alignment generation, scoped to a single run.

```cypher
// Parameters (set these before running the query)
// :param run_id           => 'RUN_ID_HERE'
// :param alignment_version => 'v1.0'

// ResolvedEntityCluster nodes with no ALIGNED_WITH edge for the given run and alignment version
MATCH (cluster:ResolvedEntityCluster)
WHERE cluster.run_id = $run_id
  AND NOT (cluster)-[:ALIGNED_WITH {run_id: $run_id, alignment_version: $alignment_version}]->(:CanonicalEntity)
RETURN cluster.cluster_id      AS cluster_id,
       cluster.canonical_name  AS canonical_name,
       cluster.entity_type     AS entity_type,
       cluster.normalized_text AS normalized_text
ORDER BY cluster.entity_type, cluster.canonical_name
LIMIT 50;
```

---

**Full alignment-to-claim chain health check** — combines alignment coverage and participation
coverage in a single query to confirm the end-to-end canonical → cluster → mention → claim path
is intact (hybrid mode) for a given alignment run.

```cypher
// End-to-end chain: for each CanonicalEntity, count reachable claims via hybrid path
// (scoped to $run_id and $alignment_version)
MATCH (canonical:CanonicalEntity)<-[a:ALIGNED_WITH]-(cluster:ResolvedEntityCluster)<-[:MEMBER_OF]-(m:EntityMention)
WHERE a.run_id = $run_id
  AND a.alignment_version = $alignment_version
  AND cluster.run_id = $run_id
  AND m.run_id = $run_id
OPTIONAL MATCH (c:ExtractedClaim {run_id: $run_id})-[:HAS_PARTICIPANT]->(m)
WITH canonical, count(DISTINCT m) AS mention_count, count(DISTINCT c) AS claim_count
RETURN canonical.name        AS canonical_entity,
       canonical.entity_type AS entity_type,
       mention_count,
       claim_count,
       CASE WHEN claim_count = 0 THEN 'dark' ELSE 'active' END AS status
ORDER BY claim_count DESC
LIMIT 30;
```

**Interpretation:** `status = 'active'` canonical entities have at least one reachable claim
through the hybrid traversal path. `status = 'dark'` canonical entities are aligned to clusters
but none of those cluster members appear as participants in any extracted claim — typically
because the entity was present in the structured catalog but did not appear in the unstructured
source document, or because the claim-participation stage could not resolve a match.

---

## How to use this workbook in Neo4j Browser

1. Open Neo4j Browser at `http://localhost:7474`.
2. Copy any query block above and paste it into the editor (the text box at the top).
3. Press **Ctrl+Enter** (or the play button) to run the query.
4. Use the **⭐ Save** button to add a query to your Saved Scripts for quick re-use.

> **Tip:** For the signature queries in sections 2–3, replace the `CONTAINS` filter value with
> any entity name from your dataset.  Entity names come from the raw LLM extraction output and
> may vary in casing and spelling; `toLower(...) CONTAINS '...'` is a safe starting point.

---

## 13. Repeatable graph-health diagnostics artifact

The queries in section 12 are also available as a repeatable, scriptable diagnostic
tool.  Running `pipelines/query/graph_health_diagnostics.py` executes all queries
in one pass and writes a scoped JSON artifact to disk that can be committed,
compared across runs, and used for regression tracking.

### Generating the artifact

```bash
# Set Neo4j connection environment variables
export NEO4J_URI=bolt://localhost:7687
export NEO4J_USERNAME=neo4j
export NEO4J_PASSWORD=<your-password>
export NEO4J_DATABASE=neo4j   # optional, defaults to 'neo4j'

# Scoped to a specific run and alignment version (recommended after each pipeline run)
python pipelines/query/graph_health_diagnostics.py \
    --run-id unstructured_ingest-20240601T120000000000Z-abcd1234 \
    --alignment-version v1.0

# Unscoped — aggregates across all runs in the database
python pipelines/query/graph_health_diagnostics.py
```

The artifact is written to:

- **Scoped run:** `pipelines/runs/<run-id>/graph_health/graph_health_diagnostics.json`
- **Unscoped:** `pipelines/runs/graph_health/graph_health_diagnostics.json`

A documented example output is available at
`pipelines/query/graph_health_example_output.json`.

### Artifact structure

The artifact is a JSON document with the following top-level keys:

| Key | Type | Description |
|-----|------|-------------|
| `generated_at` | string | ISO-8601 UTC timestamp |
| `run_id` | string \| null | Pipeline run_id scope (null = all runs) |
| `alignment_version` | string \| null | Alignment version scope |
| `participation_role_distribution` | array | Raw rows: `role`, `total` |
| `claim_edge_coverage_distribution` | array | Raw rows: `participant_edges`, `claim_count` |
| `match_method_distribution` | array | Raw rows: `match_method`, `total` |
| `mention_clustering` | array | Raw rows: `is_clustered`, `mention_count` |
| `cluster_size_distribution` | array | Raw rows: `member_count`, `cluster_count` |
| `cluster_type_fragmentation` | array | Raw rows: `distinct_types_in_cluster`, `cluster_count` |
| `alignment_coverage` | array | Raw rows: `is_aligned`, `cluster_count` |
| `per_canonical_alignment` | array | Top 30 canonical entities with aligned cluster/mention counts |
| `canonical_chain_health` | array | Top 30 canonicals with end-to-end claim-reachability status |
| `participation_summary` | object | Derived summary (see below) |
| `mention_summary` | object | Derived summary (see below) |
| `alignment_summary` | object | Derived summary (see below) |

**`participation_summary`**

| Field | Description |
|-------|-------------|
| `total_edges` | Total `HAS_PARTICIPANT` edges in scope |
| `edges_by_role` | Edge count keyed by role (`subject`, `object`, …) |
| `total_claims` | Total `ExtractedClaim` nodes in scope |
| `claims_with_zero_edges` | Claims with no participation link |
| `claim_coverage_pct` | Percentage of claims with at least one edge (null if no claims) |

**`mention_summary`**

| Field | Description |
|-------|-------------|
| `total_mentions` | Total `EntityMention` nodes in scope |
| `clustered_mentions` | Mentions with a `MEMBER_OF` edge |
| `unclustered_mentions` | Mentions without any `MEMBER_OF` edge |
| `unresolved_rate_pct` | Percentage of unclustered mentions (null if no mentions) |

**`alignment_summary`**

| Field | Description |
|-------|-------------|
| `total_clusters` | Total `ResolvedEntityCluster` nodes in scope |
| `aligned_clusters` | Clusters with an `ALIGNED_WITH` edge for the scoped version |
| `unaligned_clusters` | Clusters without an `ALIGNED_WITH` edge |
| `alignment_coverage_pct` | Percentage of aligned clusters (null if no clusters) |

### Interpreting the metrics

| Metric | Healthy signal | Suspicious movement |
|--------|---------------|---------------------|
| `claim_coverage_pct` | ≥ 85 % for a well-populated corpus | Drop of > 5 pp between runs |
| `edges_by_role` — balance | `subject` and `object` counts within ~20 % of each other | One role near zero while the other is large |
| `match_method_distribution` | `raw_exact` is the dominant method | `list_split` growing rapidly (composite spans proliferating) |
| `unresolved_rate_pct` | < 10 % in `hybrid` / `unstructured_only` mode | > 30 % may indicate entity-resolution stage did not complete |
| `cluster_type_fragmentation` — `distinct_types_in_cluster = 1` | All or nearly all clusters | More than a few `> 1` clusters signals over-aggressive fuzzy merging |
| `cluster_size_distribution` — singletons | Some singletons are normal (rare entities) | > 80 % singletons may indicate normalization thresholds too strict |
| `alignment_coverage_pct` | Proportional to the size of the structured catalog | 0 % after a hybrid run means the alignment stage did not run |
| `canonical_chain_health` — `status = 'dark'` | A small number of dark canonicals is normal | Many dark canonicals = structured catalog not contributing to retrieval |

> **Note on `unresolved_rate_pct` in structured-anchor mode:** In
> `structured_anchor` mode, mentions resolved via `RESOLVES_TO` intentionally
> have no `MEMBER_OF` edge and will appear as unclustered.  A high
> unclustered rate in that mode is expected and is *not* a bug.

### Comparing artifacts across runs

The artifact is plain JSON and can be diffed directly:

```bash
diff \
  pipelines/runs/run-a/graph_health/graph_health_diagnostics.json \
  pipelines/runs/run-b/graph_health/graph_health_diagnostics.json
```

For a focused summary comparison, use `jq`:

```bash
jq '{run_id, participation_summary, mention_summary, alignment_summary}' \
  pipelines/runs/<run-id>/graph_health/graph_health_diagnostics.json
```

### Programmatic usage

The diagnostics are also available as a Python function for use in notebooks
or custom scripts:

```python
from pathlib import Path

from demo.contracts.runtime import Config
from demo.stages.graph_health import run_graph_health_diagnostics

config = Config(
    dry_run=False,
    output_dir=Path("pipelines"),
    neo4j_uri="bolt://localhost:7687",
    neo4j_username="neo4j",
    neo4j_password="<password>",
    neo4j_database="neo4j",
    openai_model="",
)

result = run_graph_health_diagnostics(
    config,
    run_id="unstructured_ingest-...",
    alignment_version="v1.0",
)
print(result["artifact"]["participation_summary"])
```
