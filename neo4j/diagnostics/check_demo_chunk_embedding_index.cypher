// Verify that the current demo vector index exists and inspect its live
// metadata in the connected database.

SHOW INDEXES YIELD name, type, state, entityType, labelsOrTypes, properties, options
WHERE name = 'demo_chunk_embedding_index'
RETURN
  name,
  type,
  state,
  entityType,
  labelsOrTypes,
  properties,
  options;