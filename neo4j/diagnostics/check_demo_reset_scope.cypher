// Inspect the live graph footprint that the current demo reset would target.
// This query is read-only and returns node counts for the current reset-owned
// labels.

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