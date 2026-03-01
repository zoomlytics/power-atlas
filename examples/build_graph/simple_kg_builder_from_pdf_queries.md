// 0) Basic “did anything get written?”
MATCH (n)
RETURN labels(n) AS labels, count(*) AS c
ORDER BY c DESC;

// 1) Relationship types + counts (helps verify extraction happened)
MATCH ()-[r]->()
RETURN type(r) AS rel_type, count(*) AS c
ORDER BY c DESC;

// 2) Confirm expected labels exist (from the upstream PDF example schema)
MATCH (n)
WHERE any(l IN labels(n) WHERE l IN ["Person","Organization","Location","Document","Chunk"])
RETURN labels(n) AS labels, count(*) AS c
ORDER BY c DESC;

// 3) Show latest Document node(s) (PDF runs should create these)
MATCH (d:Document)
RETURN d
ORDER BY coalesce(d.createdAt, d.created_at, d.timestamp) DESC
LIMIT 5;

// 4) Check Chunk nodes exist
MATCH (c:Chunk)
RETURN c
LIMIT 5;

// 5) Ensure chunks connect back to a document (relationship name is commonly FROM_DOCUMENT)
MATCH (d:Document)<-[r]-(c:Chunk)
RETURN type(r) AS rel, count(*) AS c
ORDER BY c DESC;

// 6) Inspect a single document with a few of its chunks
MATCH (d:Document)<-[:FROM_DOCUMENT]-(c:Chunk)
RETURN d, c
LIMIT 25;

// 7) Spot-check extracted entities connected to chunks (often you’ll see “MENTIONS”/similar)
// This is intentionally generic: it shows any outgoing rels from Chunk.
MATCH (c:Chunk)-[r]->(x)
RETURN type(r) AS rel, labels(x) AS x_labels, count(*) AS c
ORDER BY c DESC;

// 7b) Confirm provenance on entities uses the chunk+document ids written by the lexical pipeline
MATCH (e)-[:FROM_CHUNK]->(c:Chunk)-[:FROM_DOCUMENT]->(d:Document)
RETURN labels(e) AS entity_labels, collect(DISTINCT d.path) AS document_paths, count(*) AS c
ORDER BY c DESC, document_paths
LIMIT 10;

// 7c) Example resolver pre-filter scope (same pattern used by script)
// WHERE (entity)-[:FROM_CHUNK]->(:Chunk)-[:FROM_DOCUMENT]->(doc:Document)
//   AND doc.path IN ["/absolute/path/to/doc.pdf"]

// 8) Sample a few Person/Organization/Location nodes
MATCH (p:Person) RETURN p LIMIT 10;
MATCH (o:Organization) RETURN o LIMIT 10;
MATCH (l:Location) RETURN l LIMIT 10;

// 9) Visualize a small subgraph around one entity (pick any name you see from queries above)
//all people
MATCH (p:Person)-[r]-(x)
RETURN p, r, x
LIMIT 50;

//one person
MATCH (p:Person {name: "Harry Potter"})-[r]-(x)
RETURN p, r, x
LIMIT 50;
