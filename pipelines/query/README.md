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

### 1a. Basic participation edge validation

```cypher
// Subject edges — check that HAS_SUBJECT_MENTION edges are present
MATCH (c:ExtractedClaim)-[r:HAS_SUBJECT_MENTION]->(m:EntityMention)
RETURN c.claim_id, c.claim_text, r.match_method, m.name
LIMIT 25;
```

```cypher
// Object edges — check that HAS_OBJECT_MENTION edges are present
MATCH (c:ExtractedClaim)-[r:HAS_OBJECT_MENTION]->(m:EntityMention)
RETURN c.claim_id, c.claim_text, r.match_method, m.name
LIMIT 25;
```

```cypher
// Combined edge summary — one row per edge type
MATCH ()-[r:HAS_SUBJECT_MENTION|HAS_OBJECT_MENTION]->()
RETURN type(r) AS edge_type, count(r) AS total
ORDER BY edge_type;
```

```cypher
// Full claim view — subject AND object mentions together
MATCH (subj:EntityMention)<-[sr:HAS_SUBJECT_MENTION]-(c:ExtractedClaim)-[obj_r:HAS_OBJECT_MENTION]->(obj:EntityMention)
RETURN c.claim_id,
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
2. The claim-participation stage ran (check for `subject_edges > 0` or `object_edges > 0` in the
   participation manifest, or re-run `extract-claims` which includes participation in the same pass).
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

```cypher
// Clusters aligned to a canonical entity — confirm hybrid enrichment
MATCH (cluster:ResolvedEntityCluster)-[a:ALIGNED_WITH]->(canonical:CanonicalEntity)
RETURN cluster.canonical_name, canonical.name, a.alignment_method, a.alignment_status
ORDER BY canonical.name;
```

```cypher
// Claims reachable from a canonical entity via cluster membership
MATCH (canonical:CanonicalEntity)<-[:ALIGNED_WITH]-(cluster:ResolvedEntityCluster)<-[:MEMBER_OF]-(m:EntityMention)
WHERE toLower(canonical.name) CONTAINS 'mercadolibre'
MATCH (c:ExtractedClaim)-[:HAS_SUBJECT_MENTION|HAS_OBJECT_MENTION]->(m)
RETURN c.claim_text, c.predicate, m.name AS mention, canonical.name AS canonical
ORDER BY c.claim_id;
```

```cypher
// Full cluster → mention → claim chain for Marcos Galperin (post-hybrid)
MATCH (canonical:CanonicalEntity)<-[:ALIGNED_WITH]-(cluster:ResolvedEntityCluster)<-[:MEMBER_OF]-(m:EntityMention)
WHERE toLower(canonical.name) CONTAINS 'galperin'
MATCH (c:ExtractedClaim)-[:HAS_SUBJECT_MENTION|HAS_OBJECT_MENTION]->(m)
RETURN canonical.name AS canonical_entity,
       cluster.canonical_name AS cluster_name,
       m.name AS mention,
       c.claim_text
ORDER BY c.claim_id;
```

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

## How to use this workbook in Neo4j Browser

1. Open Neo4j Browser at `http://localhost:7474`.
2. Copy any query block above and paste it into the editor (the text box at the top).
3. Press **Ctrl+Enter** (or the play button) to run the query.
4. Use the **⭐ Save** button to add a query to your Saved Scripts for quick re-use.

> **Tip:** For the signature queries in sections 2–3, replace the `CONTAINS` filter value with
> any entity name from your dataset.  Entity names come from the raw LLM extraction output and
> may vary in casing and spelling; `toLower(...) CONTAINS '...'` is a safe starting point.
