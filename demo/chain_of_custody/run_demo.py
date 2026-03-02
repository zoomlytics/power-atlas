from __future__ import annotations

import argparse
import csv
import json
import os
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures"
ARTIFACTS_DIR = Path(__file__).resolve().parent / "artifacts"
DEFAULT_DB = os.getenv("NEO4J_DATABASE", "neo4j")


@dataclass(frozen=True)
class DemoConfig:
    dry_run: bool
    output_dir: Path
    neo4j_uri: str
    neo4j_username: str
    neo4j_password: str
    neo4j_database: str
    openai_model: str


def _timestamp() -> str:
    return datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")


def _load_csv_rows(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def _run_structured_ingest(config: DemoConfig) -> dict[str, Any]:
    claims_path = FIXTURES_DIR / "structured" / "claims.csv"
    entities_path = FIXTURES_DIR / "structured" / "entities.csv"
    relationships_path = FIXTURES_DIR / "structured" / "relationships.csv"

    claims = _load_csv_rows(claims_path)
    entities = _load_csv_rows(entities_path)
    relationships = _load_csv_rows(relationships_path)

    if config.dry_run:
        return {
            "status": "dry_run",
            "claims": len(claims),
            "entities": len(entities),
            "relationships": len(relationships),
        }

    import neo4j

    driver = neo4j.GraphDatabase.driver(
        config.neo4j_uri,
        auth=(config.neo4j_username, config.neo4j_password),
    )
    with driver, driver.session(database=config.neo4j_database) as session:
        session.run(
            """
            UNWIND $entities AS row
            MERGE (e:CanonicalEntity {entity_id: row.entity_id})
            SET e.name = row.name, e.entity_type = row.entity_type
            """,
            entities=entities,
        ).consume()
        session.run(
            """
            UNWIND $claims AS row
            MERGE (c:Claim {claim_id: row.claim_id})
            SET c.claim_text = row.claim_text,
                c.confidence = toFloat(row.confidence),
                c.source_uri = row.source_uri
            """,
            claims=claims,
        ).consume()
        session.run(
            """
            UNWIND $rels AS row
            MATCH (a:CanonicalEntity {entity_id: row.source_entity_id})
            MATCH (b:CanonicalEntity {entity_id: row.target_entity_id})
            MERGE (a)-[r:ASSERTS_RELATIONSHIP {relationship_id: row.relationship_id}]->(b)
            SET r.relation_type = row.relation_type, r.evidence_claim_id = row.evidence_claim_id
            """,
            rels=relationships,
        ).consume()

    return {
        "status": "ingested",
        "claims": len(claims),
        "entities": len(entities),
        "relationships": len(relationships),
    }


def _run_pdf_ingest(config: DemoConfig) -> dict[str, Any]:
    pdf_path = FIXTURES_DIR / "unstructured" / "chain_of_custody.pdf"

    if config.dry_run:
        return {
            "status": "dry_run",
            "documents": [str(pdf_path)],
            "vendor_pattern": "SimpleKGPipeline + OpenAIEmbeddings + FixedSizeSplitter",
        }

    from neo4j_graphrag.embeddings import OpenAIEmbeddings
    from neo4j_graphrag.experimental.components.text_splitters.fixed_size_splitter import (
        FixedSizeSplitter,
    )
    from neo4j_graphrag.llm import OpenAILLM

    # Keep run-time configuration explicit and aligned with vendor-resources/examples.
    splitter = FixedSizeSplitter(chunk_size=1000, chunk_overlap=100, approximate=True)
    embedder = OpenAIEmbeddings(model="text-embedding-3-small")
    llm = OpenAILLM(model_name=config.openai_model)

    return {
        "status": "configured",
        "documents": [str(pdf_path)],
        "pipeline_components": [
            splitter.__class__.__name__,
            embedder.__class__.__name__,
            llm.__class__.__name__,
        ],
        "note": "Runtime ingest uses vendor pipeline components; keep in dry-run for local smoke tests.",
    }


def _run_claim_and_mention_extraction(config: DemoConfig) -> dict[str, Any]:
    if config.dry_run:
        return {
            "status": "dry_run",
            "claim_extraction": "planned",
            "mention_resolution": "deterministic by canonical entity_id",
        }
    return {
        "status": "configured",
        "claim_extraction": "LLMEntityRelationExtractor",
        "mention_resolution": "SinglePropertyExactMatchResolver",
    }


def _run_retrieval_and_qa(config: DemoConfig) -> dict[str, Any]:
    if config.dry_run:
        return {
            "status": "dry_run",
            "retrievers": ["VectorCypherRetriever", "graph expansion"],
            "qa": "GraphRAG strict citations",
        }
    return {
        "status": "configured",
        "retrievers": ["VectorCypherRetriever", "Text2CypherRetriever"],
        "qa": "GraphRAG prompt template with strict citation suffix",
    }


def run_demo(config: DemoConfig) -> Path:
    config.output_dir.mkdir(parents=True, exist_ok=True)

    manifest = {
        "run_id": f"chain-of-custody-{_timestamp()}",
        "created_at": datetime.now(UTC).isoformat(),
        "config": {
            "dry_run": config.dry_run,
            "neo4j_database": config.neo4j_database,
            "openai_model": config.openai_model,
        },
        "stages": {
            "structured_ingest": _run_structured_ingest(config),
            "pdf_ingest": _run_pdf_ingest(config),
            "claim_and_mention_extraction": _run_claim_and_mention_extraction(config),
            "retrieval_and_qa": _run_retrieval_and_qa(config),
        },
    }

    manifest_path = config.output_dir / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return manifest_path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Chain of Custody demo orchestrator")
    parser.add_argument("--dry-run", action="store_true", help="Run without live Neo4j/OpenAI calls")
    parser.add_argument("--output-dir", type=Path, default=ARTIFACTS_DIR)
    parser.add_argument("--neo4j-uri", default=os.getenv("NEO4J_URI", "neo4j://localhost:7687"))
    parser.add_argument("--neo4j-username", default=os.getenv("NEO4J_USERNAME", "neo4j"))
    parser.add_argument("--neo4j-password", default=os.getenv("NEO4J_PASSWORD", "testtesttest"))
    parser.add_argument("--neo4j-database", default=DEFAULT_DB)
    parser.add_argument("--openai-model", default=os.getenv("OPENAI_MODEL", "gpt-4o-mini"))
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    config = DemoConfig(
        dry_run=args.dry_run,
        output_dir=args.output_dir,
        neo4j_uri=args.neo4j_uri,
        neo4j_username=args.neo4j_username,
        neo4j_password=args.neo4j_password,
        neo4j_database=args.neo4j_database,
        openai_model=args.openai_model,
    )
    manifest_path = run_demo(config)
    print(f"Demo manifest written to: {manifest_path}")


if __name__ == "__main__":
    main()
