// Inspect the current demo-relevant schema inventory in the connected
// database. This diagnostic is read-only and returns three result sets:
// 1. live counts for the current demo-owned labels,
// 2. index metadata for demo-relevant labels and the contract vector index,
// 3. constraint metadata for demo-relevant labels.

RETURN
  COUNT { MATCH (:Document) } AS Document,
  COUNT { MATCH (:Chunk) } AS Chunk,
  COUNT { MATCH (:CanonicalEntity) } AS CanonicalEntity,
  COUNT { MATCH (:Claim) } AS Claim,
  COUNT { MATCH (:Fact) } AS Fact,
  COUNT { MATCH (:Relationship) } AS Relationship,
  COUNT { MATCH (:Source) } AS Source,
  COUNT { MATCH (:ExtractedClaim) } AS ExtractedClaim,
  COUNT { MATCH (:EntityMention) } AS EntityMention,
  COUNT { MATCH (:UnresolvedEntity) } AS UnresolvedEntity,
  COUNT { MATCH (:ResolvedEntityCluster) } AS ResolvedEntityCluster;

SHOW INDEXES YIELD name, type, state, entityType, labelsOrTypes, properties, options
WHERE name = 'demo_chunk_embedding_index'
   OR any(label IN coalesce(labelsOrTypes, []) WHERE label IN [
     'Document',
     'Chunk',
     'CanonicalEntity',
     'Claim',
     'Fact',
     'Relationship',
     'Source',
     'ExtractedClaim',
     'EntityMention',
     'UnresolvedEntity',
     'ResolvedEntityCluster'
   ])
RETURN
  name,
  type,
  state,
  entityType,
  labelsOrTypes,
  properties,
  options
ORDER BY name;

SHOW CONSTRAINTS YIELD name, type, entityType, labelsOrTypes, properties
WHERE any(label IN coalesce(labelsOrTypes, []) WHERE label IN [
  'Document',
  'Chunk',
  'CanonicalEntity',
  'Claim',
  'Fact',
  'Relationship',
  'Source',
  'ExtractedClaim',
  'EntityMention',
  'UnresolvedEntity',
  'ResolvedEntityCluster'
])
RETURN
  name,
  type,
  entityType,
  labelsOrTypes,
  properties
ORDER BY name;