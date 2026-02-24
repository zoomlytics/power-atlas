# Knowledge Graph Build – Summary Report

## Executive Summary
This project transformed two raw CSV datasets (nodes and edges) into a clean, enriched, and production-ready knowledge graph deployed in Neo4j Aura. The resulting system supports semantic exploration, hub detection, ego-network analysis, and investigative pattern discovery across people, organizations, events, and concepts.

---

## 1. Source Data
Two input files were provided:
- **nodes.csv** – entities (people, organizations, events, concepts, technologies, etc.)
- **edges.csv** – relationships between entities

Objective: Convert these datasets into a functioning, queryable knowledge graph.

---

## 2. Data Validation
We confirmed that the datasets were graph-ready:
- No missing node IDs
- No dangling edges
- All relationship sources and targets exist
- No duplicate edges
- No self-loops

**Outcome:** Data integrity verified.

---

## 3. Normalization & Enrichment
Enhancements applied:
- Kebab-case IDs (e.g., `george-farmer`, `parler-deplatforming-2021`)
- Inferred `entity_type` (person, org, event, concept, technology, etc.)
- Added hub metrics and inferred relationships

Generated Neo4j-ready files:
- `nodes_neo4j.csv`
- `edges_neo4j.csv`

---

## 4. Import into Neo4j Aura (Data Importer)
### Nodes
- Label: `Entity`
- ID column: `id:ID`
- Remaining columns mapped as properties

### Relationships
- Single relationship type: `RELATED`
- Start: `:START_ID`
- End: `:END_ID`
- Properties:
  - `rel_type`
  - `edge_kind`
  - `edge_id`
  - `inferred` (BOOLEAN)

**Result:**
- ~50 nodes
- 222 relationships

---

## 5. Property Naming Fix
Neo4j stored IDs as `id:ID`. We standardized IDs into a clean property:

```cypher
MATCH (n)
SET n.id = n.`id:ID`;
```

Ensured all nodes have an ID:

```cypher
MATCH (n)
WHERE n.id IS NULL
SET n.id = coalesce(n.label, toString(id(n)));
```

**Standard property:** `n.id`

---

## 6. Relationship Verification
```cypher
MATCH ()-[r]->() RETURN count(r);
```
Returned: **222 relationships**

---

## 7. Semantic Relationship Validation
```cypher
MATCH ()-[r]->()
RETURN r.rel_type, count(*)
ORDER BY count(*) DESC;
```

Observed types include:
- `INFERRED_CO_NEIGHBORS`
- `FOUNDED`
- `INVOLVED_IN`
- `ASSOCIATED_WITH`

**Conclusion:** Semantic meaning preserved via `rel_type`.

---

## 8. Visualization Behavior
Aggregation-style queries return tables only.

To visualize graphs, queries must return nodes and relationships:

```cypher
MATCH (a)-[r]->(b)
RETURN a, r, b
LIMIT 50;
```

---

## 9. Hub (Central Node) Analysis
### Total Degree Hubs
```cypher
MATCH (n)
RETURN n.id AS node_id,
       COUNT { (n)--() } AS degree
ORDER BY degree DESC
LIMIT 25;
```

### Excluding Inferred Edges
```cypher
MATCH (n)
RETURN n.id AS node_id,
       COUNT { (n)-[r]-() WHERE r.rel_type <> "INFERRED_CO_NEIGHBORS" } AS degree
ORDER BY degree DESC
LIMIT 25;
```

Identified meaningful hubs such as:
- rebekah-mercer
- parler
- data-privacy
- alexander-nix

---

## 10. Ego-Network Queries (Person-Centered Views)
Example (George Farmer):

```cypher
MATCH (g {id:"george-farmer"})-[r]-(n)
WHERE r.rel_type <> "INFERRED_CO_NEIGHBORS"
RETURN g, r, n
LIMIT 100;
```

Produces a visual subgraph centered on the selected person.

---

## 11. Investigative Pattern Queries
### Organizations Bridging Multiple Scandals
```cypher
MATCH (org)
WHERE org.entity_type = "org"
MATCH (org)-[r]-(s)
WHERE r.rel_type <> "INFERRED_CO_NEIGHBORS"
  AND s.entity_type = "event"
WITH org, collect(DISTINCT s) AS scandals
WHERE size(scandals) >= 2
RETURN org.id, size(scandals), [x IN scandals | x.id];
```

### Person → Org → Event Chains
```cypher
MATCH (p {id:"george-farmer"})-[r1]-(org)-[r2]-(evt)
WHERE r1.rel_type <> "INFERRED_CO_NEIGHBORS"
  AND r2.rel_type <> "INFERRED_CO_NEIGHBORS"
RETURN p, org, evt;
```

---

## Final System Capabilities
- Clean node IDs
- Semantic relationships
- Visualizable graph
- Hub detection
- Ego networks
- Bridge analysis
- Investigative traversal patterns

**Status:** Production-grade exploratory knowledge graph.

---

## Rebuild Checklist
1. Upload nodes and edges
2. Map IDs correctly
3. Map `:TYPE` → `rel_type`
4. Copy `id:ID` → `id`
5. Verify relationships
6. Begin exploration

---

## Recommended Next Steps
- Add graph styling
- Run PageRank / community detection
- Convert `rel_type` into native Neo4j relationship types
- Build saved investigative queries

