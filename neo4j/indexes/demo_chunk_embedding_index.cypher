// Demo vector index contract for the current lexical graph pipeline.
// Keep this asset aligned with:
// - demo/config/pdf_simple_kg_pipeline.yaml
// - src/power_atlas/contracts/pipeline.py
// - demo/reset_demo_db.py

CREATE VECTOR INDEX `demo_chunk_embedding_index` IF NOT EXISTS
FOR (node:`Chunk`)
ON node.`embedding`
OPTIONS {
  indexConfig: {
    `vector.dimensions`: 1536,
    `vector.similarity_function`: 'cosine'
  }
};