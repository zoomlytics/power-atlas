# Neo4j sanity-check queries (SimpleKGPipeline example)

Use these queries in Neo4j Browser (http://localhost:7474) or via `cypher-shell` to confirm the KG builder example wrote data as expected.

## 1) Confirm APOC is installed
```cypher
RETURN apoc.version();
```

## 2) Verify the specific APOC procedure used by the writer exists
If the writer fails with `ProcedureNotFound: apoc.create.addLabels`, run:

```cypher
SHOW PROCEDURES YIELD name
WHERE name = "apoc.create.addLabels"
RETURN name;
```

## 3) Show procedure security settings (helpful when APOC exists but procedures don’t)
```cypher
SHOW SETTINGS YIELD name, value
WHERE name STARTS WITH "dbms.security.procedures"
RETURN name, value;
```

## 4) Quick “did anything get written?” check
Shows label counts across the database:

```cypher
MATCH (n)
RETURN labels(n) AS labels, count(*) AS c
ORDER BY c DESC;
```

## 5) Inspect the graph created by the example
### Find Paul and outgoing relationships
```cypher
MATCH (p:Person {name: "Paul"})-[r]->(x)
RETURN p, type(r) AS rel, x
LIMIT 50;
```

### Find the House Atreides node and its connections
```cypher
MATCH (h:House {name: "House Atreides"})-[r]-(x)
RETURN h, type(r) AS rel, x
LIMIT 50;
```

### Find any Planet nodes
```cypher
MATCH (p:Planet)
RETURN p
LIMIT 25;
```

## 6) Check for Document/Chunk nodes (pipeline provenance)
Depending on your pipeline/library version, you may see `Document` and `Chunk` nodes.

```cypher
MATCH (d:Document)
RETURN d
ORDER BY d.createdAt DESC
LIMIT 10;
```

```cypher
MATCH (c:Chunk)
RETURN c
LIMIT 10;
```

### Show how chunks relate to the document
```cypher
MATCH (d:Document)<-[:FROM_DOCUMENT]-(c:Chunk)
RETURN d, c
LIMIT 25;
```

## 7) Cleanup queries (optional)
If you want to delete everything and rerun the example:

```cypher
MATCH (n)
DETACH DELETE n;
```

If you have constraints/indexes you want to keep, prefer deleting only the labels you created (adjust as needed):

```cypher
MATCH (n:Person) DETACH DELETE n;
MATCH (n:House) DETACH DELETE n;
MATCH (n:Planet) DETACH DELETE n;
MATCH (n:Document) DETACH DELETE n;
MATCH (n:Chunk) DETACH DELETE n;
```