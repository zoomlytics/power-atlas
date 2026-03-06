from __future__ import annotations

import argparse
import os

import neo4j

from demo.contracts import CHUNK_EMBEDDING_INDEX_NAME


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Reset Chain of Custody demo nodes and indexes.")
    parser.add_argument("--confirm", action="store_true", help="required safety flag")
    parser.add_argument("--neo4j-uri", default=os.getenv("NEO4J_URI", "neo4j://localhost:7687"))
    parser.add_argument("--neo4j-username", default=os.getenv("NEO4J_USERNAME", "neo4j"))
    parser.add_argument("--neo4j-password", default=os.getenv("NEO4J_PASSWORD"))
    parser.add_argument("--neo4j-database", default=os.getenv("NEO4J_DATABASE", "neo4j"))
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if not args.confirm:
        raise SystemExit("Refusing to run without --confirm")
    if not args.neo4j_password:
        raise SystemExit("NEO4J_PASSWORD environment variable or --neo4j-password must be set")

    driver = neo4j.GraphDatabase.driver(args.neo4j_uri, auth=(args.neo4j_username, args.neo4j_password))
    with driver, driver.session(database=args.neo4j_database) as session:
        session.run(
            """
            MATCH (n)
            WHERE n:Document
               OR n:Chunk
               OR n:Claim
               OR n:CanonicalEntity
               OR n:EntityMention
            DETACH DELETE n
            """
        ).consume()

        # Keep this reset contract aligned with demo/config/pdf_simple_kg_pipeline.yaml
        # and run_demo.py deterministic vector index setup.
        for index_name in [CHUNK_EMBEDDING_INDEX_NAME]:
            if not index_name.replace("_", "").isalnum():
                raise ValueError(f"Unsafe index name: {index_name}")
            session.run(f"DROP INDEX `{index_name}` IF EXISTS").consume()

    print("Chain of Custody demo graph reset complete.")


if __name__ == "__main__":
    main()
