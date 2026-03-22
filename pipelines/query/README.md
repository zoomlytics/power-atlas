# Neo4j Browser Query Workbook — Power Atlas v0.2

This workbook contains ready-to-run Cypher queries for exploring the Power Atlas graph in Neo4j Browser.
Paste any query block directly into the Neo4j Browser editor and run it.

**Recommended traversal patterns for v0.2:** start from claim-participation edges
(`HAS_SUBJECT_MENTION` / `HAS_OBJECT_MENTION`), not chunk co-location.
Chunk co-location queries are still available for architecture-level inspection;
see [Architecture reference queries](#architecture-reference-queries-chunk-co-location) below.

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

## 1. Claim-participation queries (v0.2 — recommended)

These queries traverse `HAS_SUBJECT_MENTION` and `HAS_OBJECT_MENTION` edges — the v0.2
participation model that directly links each `ExtractedClaim` to the `EntityMention` nodes
filling its subject and object slots.  Prefer these over chunk co-location for all
claim-focused analysis.

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
// Subject edges — check that HAS_SUBJECT_MENTION edges are present
MATCH (c:ExtractedClaim)-[r:HAS_SUBJECT_MENTION]->(m:EntityMention)
RETURN c.run_id, c.claim_id, c.claim_text, r.match_method, m.name
LIMIT 25;
```

```cypher
// Object edges — check that HAS_OBJECT_MENTION edges are present
MATCH (c:ExtractedClaim)-[r:HAS_OBJECT_MENTION]->(m:EntityMention)
RETURN c.run_id, c.claim_id, c.claim_text, r.match_method, m.name
LIMIT 25;
```

```cypher
// Combined edge summary — one row per edge type (all runs)
MATCH ()-[r:HAS_SUBJECT_MENTION|HAS_OBJECT_MENTION]->()
RETURN type(r) AS edge_type, count(r) AS total
ORDER BY edge_type;
```

```cypher
// Full claim view — subject AND object mentions together
MATCH (subj:EntityMention)<-[sr:HAS_SUBJECT_MENTION]-(c:ExtractedClaim)-[obj_r:HAS_OBJECT_MENTION]->(obj:EntityMention)
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

**Interpretation notes (v0.2):**

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
MATCH (c:ExtractedClaim)-[r:HAS_SUBJECT_MENTION]->(m:EntityMention)
WHERE toLower(m.name) CONTAINS 'galperin'
RETURN c.claim_text, c.predicate, c.object, m.name AS matched_mention, r.match_method
ORDER BY c.claim_id;
```

```cypher
// All claims where Marcos Galperin appears as subject OR object
MATCH (c:ExtractedClaim)-[r:HAS_SUBJECT_MENTION|HAS_OBJECT_MENTION]->(m:EntityMention)
WHERE toLower(m.name) CONTAINS 'galperin'
RETURN c.claim_text, type(r) AS role, m.name AS matched_mention, r.match_method
ORDER BY c.claim_id;
```

### 2b. Signature query — MercadoLibre

```cypher
// All claims where MercadoLibre appears as subject
MATCH (c:ExtractedClaim)-[r:HAS_SUBJECT_MENTION]->(m:EntityMention)
WHERE toLower(m.name) CONTAINS 'mercadolibre'
RETURN c.claim_text, c.predicate, c.object, m.name AS matched_mention, r.match_method
ORDER BY c.claim_id;
```

```cypher
// All claims where MercadoLibre appears in any role
MATCH (c:ExtractedClaim)-[r:HAS_SUBJECT_MENTION|HAS_OBJECT_MENTION]->(m:EntityMention)
WHERE toLower(m.name) CONTAINS 'mercadolibre'
RETURN c.claim_text, type(r) AS role, m.name AS matched_mention, r.match_method
ORDER BY c.claim_id;
```

### 2c. General entity search

```cypher
// Replace 'endeavor' with any entity name fragment you want to search
MATCH (c:ExtractedClaim)-[r:HAS_SUBJECT_MENTION|HAS_OBJECT_MENTION]->(m:EntityMention)
WHERE toLower(m.name) CONTAINS 'endeavor'
RETURN c.claim_text, type(r) AS role, m.name AS matched_mention, r.match_method
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
MATCH (subj:EntityMention)<-[:HAS_SUBJECT_MENTION]-(c:ExtractedClaim)-[:HAS_OBJECT_MENTION]->(obj:EntityMention)
WHERE toLower(subj.name) CONTAINS 'galperin'
  AND toLower(obj.name)  CONTAINS 'mercadolibre'
RETURN c.claim_text, c.predicate, subj.name AS subject, obj.name AS object;
```

```cypher
// Claims connecting Galperin and MercadoLibre in either direction
MATCH (a:EntityMention)<-[:HAS_SUBJECT_MENTION]-(c:ExtractedClaim)-[:HAS_OBJECT_MENTION]->(b:EntityMention)
WHERE (toLower(a.name) CONTAINS 'galperin'    AND toLower(b.name) CONTAINS 'mercadolibre')
   OR (toLower(a.name) CONTAINS 'mercadolibre' AND toLower(b.name) CONTAINS 'galperin')
RETURN c.claim_text, c.predicate, a.name AS subject, b.name AS object
ORDER BY c.claim_id;
```

### 3b. General pairwise — any two entities

```cypher
// Replace the two CONTAINS filters with the entity names you want to compare
MATCH (a:EntityMention)<-[:HAS_SUBJECT_MENTION]-(c:ExtractedClaim)-[:HAS_OBJECT_MENTION]->(b:EntityMention)
WHERE (toLower(a.name) CONTAINS 'endeavor' AND toLower(b.name) CONTAINS 'mercadolibre')
   OR (toLower(a.name) CONTAINS 'mercadolibre' AND toLower(b.name) CONTAINS 'endeavor')
RETURN c.claim_text, c.predicate, a.name AS subject, b.name AS object
ORDER BY c.claim_id;
```

### 3c. All pairwise claim links (sample)

```cypher
// All claims that have both subject and object mentions — shows the full pairwise graph
MATCH (a:EntityMention)<-[:HAS_SUBJECT_MENTION]-(c:ExtractedClaim)-[:HAS_OBJECT_MENTION]->(b:EntityMention)
RETURN a.name AS subject_entity,
       c.predicate,
       b.name AS object_entity,
       c.claim_text
LIMIT 25;
```

**Interpretation notes:**

- Pairwise queries require *both* `HAS_SUBJECT_MENTION` and `HAS_OBJECT_MENTION` to be present on
  the same claim.  If one slot is missing (no unique mention match found), the claim will not
  appear in the result.
- To include claims where only one slot was resolved, use the entity-centric queries in section 2
  which match either edge type independently.

---

## 4. Cluster-aware entity traversal (post-hybrid)

These queries apply after `resolve-entities --resolution-mode hybrid` has run.

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
MATCH (c:ExtractedClaim)-[:HAS_SUBJECT_MENTION|HAS_OBJECT_MENTION]->(m)
WHERE c.run_id = $run_id
RETURN c.claim_text, c.predicate, m.name AS mention, canonical.name AS canonical
ORDER BY c.claim_id;
```

```cypher
// Full cluster → mention → claim chain for Marcos Galperin (post-hybrid, scoped to run)
MATCH (canonical:CanonicalEntity)<-[a:ALIGNED_WITH]-(cluster:ResolvedEntityCluster)<-[:MEMBER_OF]-(m:EntityMention)
WHERE toLower(canonical.name) CONTAINS 'galperin'
  AND a.run_id = $run_id AND a.alignment_version = $alignment_version
MATCH (c:ExtractedClaim)-[:HAS_SUBJECT_MENTION|HAS_OBJECT_MENTION]->(m)
WHERE c.run_id = $run_id
RETURN canonical.name AS canonical_entity,
       cluster.canonical_name AS cluster_name,
       m.name AS mention,
       c.claim_text
ORDER BY c.claim_id;
```

---

## 5. Graph-expanded retrieval — claim participation in retrieved context (v0.2)

When using `ask --expand-graph` or `ask --cluster-aware`, the graph-expanded retrieval queries
now include a `claim_details` field for each retrieved chunk.  Unlike the flat `claims` list
(which contains only claim text), `claim_details` traverses `HAS_SUBJECT_MENTION` and
`HAS_OBJECT_MENTION` edges so each claim map carries:

| Field | Description |
| --- | --- |
| `claim_text` | The full claim text |
| `subject_mention.name` | Name of the subject `EntityMention` (via `HAS_SUBJECT_MENTION`) |
| `subject_mention.match_method` | How the slot text was resolved (`raw_exact`, `casefold_exact`, `normalized_exact`) |
| `object_mention.name` | Name of the object `EntityMention` (via `HAS_OBJECT_MENTION`) |
| `object_mention.match_method` | How the slot text was resolved |

Slots without a participation edge are `null` — **no chunk co-location fallback is applied**.
The following queries mirror what the retrieval stage now materialises for each chunk.

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
        subject_mention: [(claim)-[sr:HAS_SUBJECT_MENTION]->(sm:EntityMention) | {name: sm.name, match_method: sr.match_method}][0],
        object_mention: [(claim)-[or_:HAS_OBJECT_MENTION]->(om:EntityMention) | {name: om.name, match_method: or_.match_method}][0]
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
MATCH (claim:ExtractedClaim)-[:HAS_SUBJECT_MENTION]->(m:EntityMention)
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
MATCH (claim:ExtractedClaim)-[:HAS_OBJECT_MENTION]->(m:EntityMention)
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
OPTIONAL MATCH (claim)-[sr:HAS_SUBJECT_MENTION]->(subj:EntityMention)
OPTIONAL MATCH (claim)-[or_:HAS_OBJECT_MENTION]->(obj:EntityMention)
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
`HAS_SUBJECT_MENTION` / `HAS_OBJECT_MENTION` edge exists.  `all_chunk_mentions` shows
every mention in the chunk — a superset that includes mentions unrelated to this claim.
The retrieval stage uses participation edges exclusively; it does **not** fall back to
`all_chunk_mentions` for claims that lack participation edges.

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
- Do *not* use co-location as a proxy for claim participation — use the `HAS_SUBJECT_MENTION` /
  `HAS_OBJECT_MENTION` edges instead.

---

## 6. Resolved-entity traversal (post-clustering)

These queries traverse from a `ResolvedEntityCluster` through its member `EntityMention` nodes to
the `ExtractedClaim` nodes where those mentions appear.  This cluster-based traversal is available
after `resolve-entities` and is primarily intended for `unstructured_only` / `hybrid` runs; in
`structured_anchor` mode, only *unresolved* mentions are clustered via `MEMBER_OF` (resolved
mentions use `RESOLVES_TO` and are not reachable via this pattern).

> **Traversal path:**
> ```
> (:ResolvedEntityCluster)<-[:MEMBER_OF]-(:EntityMention)<-[:HAS_SUBJECT_MENTION|HAS_OBJECT_MENTION]-(:ExtractedClaim)
> ```

> **Tip:** Set a run parameter in Neo4j Browser before running these queries:
>
> ```cypher
> :param run_id => 'your-run-id-here'
> ```
>
> Then add `AND cluster.run_id = $run_id` and `AND c.run_id = $run_id` to scope results to a
> single run.

### 6a. All claims for a cluster (subject or object)

```cypher
// All claims where any member of the MercadoLibre cluster appears — subject or object
// Replace 'mercadolibre' with any entity name fragment from your dataset
MATCH (cluster:ResolvedEntityCluster)<-[:MEMBER_OF]-(m:EntityMention)
WHERE toLower(cluster.canonical_name) CONTAINS 'mercadolibre'
  AND cluster.run_id = $run_id
  AND m.run_id = $run_id
MATCH (c:ExtractedClaim)-[r:HAS_SUBJECT_MENTION|HAS_OBJECT_MENTION]->(m)
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
MATCH (c:ExtractedClaim)-[r:HAS_SUBJECT_MENTION]->(m)
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
MATCH (c:ExtractedClaim)-[r:HAS_OBJECT_MENTION]->(m)
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
MATCH (clusterA:ResolvedEntityCluster)<-[:MEMBER_OF]-(mA:EntityMention)
WHERE toLower(clusterA.canonical_name) CONTAINS 'galperin'
  AND clusterA.run_id = $run_id
  AND mA.run_id = $run_id
MATCH (clusterB:ResolvedEntityCluster)<-[:MEMBER_OF]-(mB:EntityMention)
WHERE toLower(clusterB.canonical_name) CONTAINS 'mercadolibre'
  AND clusterB.run_id = $run_id
  AND mB.run_id = $run_id
MATCH (mA)<-[:HAS_SUBJECT_MENTION]-(c:ExtractedClaim)-[:HAS_OBJECT_MENTION]->(mB)
WHERE c.run_id = $run_id
RETURN c.claim_text,
       c.predicate,
       mA.name AS subject_mention,
       mB.name AS object_mention,
       clusterA.canonical_name AS subject_cluster,
       clusterB.canonical_name AS object_cluster
ORDER BY c.claim_id;
```

```cypher
// Bidirectional pairwise — either cluster in either role
MATCH (clusterA:ResolvedEntityCluster)<-[:MEMBER_OF]-(mA:EntityMention)
WHERE toLower(clusterA.canonical_name) CONTAINS 'galperin'
  AND clusterA.run_id = $run_id
  AND mA.run_id = $run_id
MATCH (clusterB:ResolvedEntityCluster)<-[:MEMBER_OF]-(mB:EntityMention)
WHERE toLower(clusterB.canonical_name) CONTAINS 'mercadolibre'
  AND clusterB.run_id = $run_id
  AND mB.run_id = $run_id
OPTIONAL MATCH (mA)<-[:HAS_SUBJECT_MENTION]-(cAB:ExtractedClaim)-[:HAS_OBJECT_MENTION]->(mB)
WHERE cAB.run_id = $run_id
OPTIONAL MATCH (mB)<-[:HAS_SUBJECT_MENTION]-(cBA:ExtractedClaim)-[:HAS_OBJECT_MENTION]->(mA)
WHERE cBA.run_id = $run_id
WITH collect(DISTINCT {claim_id: cAB.claim_id, claim_text: cAB.claim_text, predicate: cAB.predicate,
                        subject: mA.name, object: mB.name, direction: 'A→B'}) +
     collect(DISTINCT {claim_id: cBA.claim_id, claim_text: cBA.claim_text, predicate: cBA.predicate,
                        subject: mB.name, object: mA.name, direction: 'B→A'}) AS all_claims
UNWIND all_claims AS claim
WITH claim WHERE claim.claim_text IS NOT NULL
RETURN claim.claim_id, claim.claim_text, claim.predicate, claim.subject, claim.object, claim.direction
ORDER BY claim.direction, claim.claim_text;
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
MATCH (c:ExtractedClaim)-[r:HAS_SUBJECT_MENTION|HAS_OBJECT_MENTION]->(m)
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
MATCH (c:ExtractedClaim)-[r:HAS_SUBJECT_MENTION]->(m)
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
MATCH (c:ExtractedClaim)-[r:HAS_SUBJECT_MENTION|HAS_OBJECT_MENTION]->(m)
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
MATCH (c:ExtractedClaim)-[r:HAS_SUBJECT_MENTION]->(m)
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
MATCH (canonA:CanonicalEntity)<-[aA:ALIGNED_WITH]-(clA:ResolvedEntityCluster)<-[:MEMBER_OF]-(mA:EntityMention)
WHERE toLower(canonA.name) CONTAINS 'galperin'
  AND aA.run_id = $run_id AND aA.alignment_version = $alignment_version
  AND mA.run_id = $run_id
MATCH (canonB:CanonicalEntity)<-[aB:ALIGNED_WITH]-(clB:ResolvedEntityCluster)<-[:MEMBER_OF]-(mB:EntityMention)
WHERE toLower(canonB.name) CONTAINS 'mercadolibre'
  AND aB.run_id = $run_id AND aB.alignment_version = $alignment_version
  AND mB.run_id = $run_id
MATCH (mA)<-[:HAS_SUBJECT_MENTION]-(c:ExtractedClaim)-[:HAS_OBJECT_MENTION]->(mB)
WHERE c.run_id = $run_id
RETURN c.claim_text,
       c.predicate,
       mA.name       AS subject_mention,
       mB.name       AS object_mention,
       canonA.name   AS subject_canonical,
       canonB.name   AS object_canonical
ORDER BY c.claim_id;
```

```cypher
// Bidirectional pairwise — either canonical entity in either role (hybrid mode)
MATCH (canonA:CanonicalEntity)<-[aA:ALIGNED_WITH]-(clA:ResolvedEntityCluster)<-[:MEMBER_OF]-(mA:EntityMention)
WHERE toLower(canonA.name) CONTAINS 'galperin'
  AND aA.run_id = $run_id
  AND aA.alignment_version = $alignment_version
  AND mA.run_id = $run_id
MATCH (canonB:CanonicalEntity)<-[aB:ALIGNED_WITH]-(clB:ResolvedEntityCluster)<-[:MEMBER_OF]-(mB:EntityMention)
WHERE toLower(canonB.name) CONTAINS 'mercadolibre'
  AND aB.run_id = $run_id
  AND aB.alignment_version = $alignment_version
  AND mB.run_id = $run_id
OPTIONAL MATCH (mA)<-[:HAS_SUBJECT_MENTION]-(cAB:ExtractedClaim)-[:HAS_OBJECT_MENTION]->(mB)
WHERE cAB.run_id = $run_id
OPTIONAL MATCH (mB)<-[:HAS_SUBJECT_MENTION]-(cBA:ExtractedClaim)-[:HAS_OBJECT_MENTION]->(mA)
WHERE cBA.run_id = $run_id
WITH collect(DISTINCT {claim_id: cAB.claim_id, claim_text: cAB.claim_text, predicate: cAB.predicate,
                        subject: mA.name, object: mB.name, direction: 'A→B'}) +
     collect(DISTINCT {claim_id: cBA.claim_id, claim_text: cBA.claim_text, predicate: cBA.predicate,
                        subject: mB.name, object: mA.name, direction: 'B→A'}) AS all_claims
UNWIND all_claims AS claim
WITH claim WHERE claim.claim_text IS NOT NULL
RETURN claim.claim_id, claim.claim_text, claim.predicate, claim.subject, claim.object, claim.direction
ORDER BY claim.direction, claim.claim_text, claim.claim_id;
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
MATCH (c:ExtractedClaim)-[:HAS_SUBJECT_MENTION|HAS_OBJECT_MENTION]->(m)
WHERE c.run_id = $run_id
RETURN cluster.canonical_name AS cluster,
       cluster.entity_type,
       count(DISTINCT c) AS claim_count,
       count(DISTINCT m) AS mention_count
ORDER BY claim_count DESC
LIMIT 20;
```

```cypher
// Claim count per cluster, broken down by subject vs. object role
MATCH (cluster:ResolvedEntityCluster)<-[:MEMBER_OF]-(m:EntityMention)
WHERE cluster.run_id = $run_id
  AND m.run_id = $run_id
MATCH (c:ExtractedClaim)-[r:HAS_SUBJECT_MENTION|HAS_OBJECT_MENTION]->(m)
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
MATCH (c:ExtractedClaim)-[:HAS_SUBJECT_MENTION|HAS_OBJECT_MENTION]->(m)
WHERE c.run_id = $run_id
RETURN canonical.name       AS canonical_entity,
       canonical.entity_id,
       count(DISTINCT c)    AS claim_count,
       count(DISTINCT m)    AS mention_count,
       count(DISTINCT cluster) AS cluster_count
ORDER BY claim_count DESC
LIMIT 20;
```

### 8c. Cluster-to-claim coverage summary

```cypher
// How many clusters have at least one associated claim? How many are 'dark' (no claims)?
MATCH (cluster:ResolvedEntityCluster)
WHERE cluster.run_id = $run_id
OPTIONAL MATCH (cluster)<-[:MEMBER_OF]-(m:EntityMention)<-[:HAS_SUBJECT_MENTION|HAS_OBJECT_MENTION]-(c:ExtractedClaim)
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
MATCH (c:ExtractedClaim)-[r:HAS_SUBJECT_MENTION|HAS_OBJECT_MENTION]->(m)
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
MATCH (c:ExtractedClaim)-[:HAS_OBJECT_MENTION]->(mObj)
WHERE c.run_id = $run_id
MATCH (c)-[:HAS_SUBJECT_MENTION]->(mSubj:EntityMention)
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
MATCH (c:ExtractedClaim)-[r:HAS_SUBJECT_MENTION|HAS_OBJECT_MENTION]->(m)
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

## 10. Derived edge analysis — materializing claim→cluster and claim→canonical edges

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
- The 2–3 hop traversal is manageable with standard Neo4j indexes on `run_id`, `cluster_id`, and
  `entity_id`.  For the data volumes targeted by v0.1, these queries run well within interactive
  latency budgets.
- Materialized edges duplicate information already encoded in participation edges
  (`HAS_SUBJECT_MENTION` / `HAS_OBJECT_MENTION`) and resolution edges (`MEMBER_OF` /
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

## How to use this workbook in Neo4j Browser

1. Open Neo4j Browser at `http://localhost:7474`.
2. Copy any query block above and paste it into the editor (the text box at the top).
3. Press **Ctrl+Enter** (or the play button) to run the query.
4. Use the **⭐ Save** button to add a query to your Saved Scripts for quick re-use.

> **Tip:** For the signature queries in sections 2–3, replace the `CONTAINS` filter value with
> any entity name from your dataset.  Entity names come from the raw LLM extraction output and
> may vary in casing and spelling; `toLower(...) CONTAINS '...'` is a safe starting point.
