# Versioned constants for entity resolution pipeline outputs.
# Imported by both demo.stages.entity_resolution and demo.stages.retrieval_and_qa
# so that ALIGNED_WITH edge filtering and edge creation always use the same value.

# Bump this constant whenever the cluster-to-canonical alignment logic changes so
# that ALIGNED_WITH edges can be distinguished by the version that created them.
ALIGNMENT_VERSION: str = "v1.0"
