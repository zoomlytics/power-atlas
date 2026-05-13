from __future__ import annotations

from typing import Any

from power_atlas.contracts import (
    StructuredGraphShapeContract,
    get_default_structured_graph_shape_contract,
)


def _escape_cypher_identifier(value: str) -> str:
    if not value or "`" in value:
        raise ValueError(f"Invalid Cypher identifier {value!r}")
    return f"`{value}`"


def _asserted_in_clause(
    node_var: str,
    *,
    retrieved_at_expr: str,
    graph_shape: StructuredGraphShapeContract,
) -> str:
    return (
        f"WITH {node_var}, row\n"
        "        MATCH (dataset:{source_label} {{source_key: $source_uri, run_id: $run_id}})\n"
        "        MERGE ({node_var})-[asserted_in:{asserted_in_relationship}]->(dataset)\n"
        "        SET asserted_in.run_id = $run_id,\n"
        "            asserted_in.source_uri = $source_uri,\n"
        f"            asserted_in.retrieved_at = {retrieved_at_expr}\n"
    ).format(
        node_var=node_var,
        source_label=_escape_cypher_identifier(graph_shape.source_label),
        asserted_in_relationship=_escape_cypher_identifier(
            graph_shape.asserted_in_relationship
        ),
    )


def _row_source_clause(
    node_var: str,
    *,
    retrieved_at_expr: str,
    graph_shape: StructuredGraphShapeContract,
) -> str:
    return (
        "FOREACH (_ IN CASE WHEN coalesce(row.source_url, '') = '' THEN [] ELSE [1] END |\n"
        "            MERGE (source:{source_label} {{source_key: row.source_url, run_id: $run_id}})\n"
        "            SET source.source_type = 'row_source',\n"
        "                source.source = row.source,\n"
        f"                source.retrieved_at = {retrieved_at_expr},\n"
        "                source.source_uri = $source_uri\n"
        "            MERGE ({node_var})-[cited_from:{cited_from_relationship}]->(source)\n"
        "            SET cited_from.run_id = $run_id,\n"
        "                cited_from.source_uri = $source_uri,\n"
        f"                cited_from.retrieved_at = {retrieved_at_expr}\n"
        "        )\n"
    ).format(
        node_var=node_var,
        source_label=_escape_cypher_identifier(graph_shape.source_label),
        cited_from_relationship=_escape_cypher_identifier(
            graph_shape.cited_from_relationship
        ),
    )


def _write_dataset_source(
    session: Any,
    *,
    run_id: str,
    source_uri: str,
    dataset_id: str,
    ingested_at: str,
    graph_shape: StructuredGraphShapeContract,
) -> None:
    session.run(
        """
        MERGE (dataset:{source_label} {{source_key: $source_uri, run_id: $run_id}})
        SET dataset.source_type = 'dataset',
            dataset.dataset_id = $dataset_id,
            dataset.retrieved_at = $ingested_at,
            dataset.source_uri = $source_uri
        """.format(
            source_label=_escape_cypher_identifier(graph_shape.source_label)
        ),
        source_uri=source_uri,
        run_id=run_id,
        dataset_id=dataset_id,
        ingested_at=ingested_at,
    ).consume()


def _write_entities(
    session: Any,
    *,
    rows: list[dict[str, str]],
    run_id: str,
    source_uri: str,
    dataset_id: str,
    ingested_at: str,
    graph_shape: StructuredGraphShapeContract,
) -> None:
    asserted_in_clause = _asserted_in_clause(
        "entity",
        retrieved_at_expr="$ingested_at",
        graph_shape=graph_shape,
    )
    session.run(
        """
        UNWIND $rows AS row
        MERGE (entity:{entity_label} {{entity_id: trim(row.entity_id), run_id: $run_id}})
        SET entity.name = row.name,
            entity.entity_type = row.entity_type,
            entity.aliases = row.aliases,
            entity.description = row.description,
            entity.wikidata_url = row.wikidata_url,
            entity.source_uri = $source_uri,
            entity.dataset_id = $dataset_id,
            entity.retrieved_at = $ingested_at
        {asserted_in_clause}""".format(
            entity_label=_escape_cypher_identifier(graph_shape.entity_label),
            asserted_in_clause=asserted_in_clause,
        ),
        rows=rows,
        run_id=run_id,
        source_uri=source_uri,
        dataset_id=dataset_id,
        ingested_at=ingested_at,
    ).consume()


def _write_facts(
    session: Any,
    *,
    rows: list[dict[str, str]],
    run_id: str,
    source_uri: str,
    dataset_id: str,
    ingested_at: str,
    graph_shape: StructuredGraphShapeContract,
) -> None:
    asserted_in_clause = _asserted_in_clause(
        "fact",
        retrieved_at_expr="coalesce(row.retrieved_at, $ingested_at)",
        graph_shape=graph_shape,
    )
    row_source_clause = _row_source_clause(
        "fact",
        retrieved_at_expr="coalesce(row.retrieved_at, $ingested_at)",
        graph_shape=graph_shape,
    )
    session.run(
        """
        UNWIND $rows AS row
        MERGE (fact:{fact_label} {{fact_id: trim(row.fact_id), run_id: $run_id}})
        SET fact.subject_id = trim(row.subject_id),
            fact.subject_label = row.subject_label,
            fact.predicate_pid = row.predicate_pid,
            fact.predicate_label = row.predicate_label,
            fact.value = row.value,
            fact.value_type = row.value_type,
            fact.source = row.source,
            fact.source_url = row.source_url,
            fact.retrieved_at = row.retrieved_at,
            fact.source_uri = $source_uri,
            fact.dataset_id = $dataset_id
        MERGE (subject:{entity_label} {{entity_id: trim(row.subject_id), run_id: $run_id}})
        ON CREATE SET subject.name = row.subject_label,
                      subject.source_uri = $source_uri,
                      subject.dataset_id = $dataset_id,
                      subject.retrieved_at = coalesce(row.retrieved_at, $ingested_at)
        MERGE (fact)-[about:{about_relationship}]->(subject)
        SET about.run_id = $run_id,
            about.source_uri = $source_uri,
            about.retrieved_at = coalesce(row.retrieved_at, $ingested_at)
        {asserted_in_clause}        {row_source_clause}""".format(
            fact_label=_escape_cypher_identifier(graph_shape.fact_label),
            entity_label=_escape_cypher_identifier(graph_shape.entity_label),
            about_relationship=_escape_cypher_identifier(
                graph_shape.about_relationship
            ),
            asserted_in_clause=asserted_in_clause,
            row_source_clause=row_source_clause,
        ),
        rows=rows,
        run_id=run_id,
        source_uri=source_uri,
        dataset_id=dataset_id,
        ingested_at=ingested_at,
    ).consume()


def _write_relationships(
    session: Any,
    *,
    rows: list[dict[str, str]],
    run_id: str,
    source_uri: str,
    dataset_id: str,
    ingested_at: str,
    graph_shape: StructuredGraphShapeContract,
) -> None:
    asserted_in_clause = _asserted_in_clause(
        "relationship",
        retrieved_at_expr="coalesce(row.retrieved_at, $ingested_at)",
        graph_shape=graph_shape,
    )
    row_source_clause = _row_source_clause(
        "relationship",
        retrieved_at_expr="coalesce(row.retrieved_at, $ingested_at)",
        graph_shape=graph_shape,
    )
    session.run(
        """
        UNWIND $rows AS row
        MERGE (relationship:{relationship_label} {{rel_id: trim(row.rel_id), run_id: $run_id}})
        SET relationship.subject_id = trim(row.subject_id),
            relationship.subject_label = row.subject_label,
            relationship.predicate_pid = row.predicate_pid,
            relationship.predicate_label = row.predicate_label,
            relationship.object_id = trim(row.object_id),
            relationship.object_label = row.object_label,
            relationship.object_entity_type = row.object_entity_type,
            relationship.source = row.source,
            relationship.source_url = row.source_url,
            relationship.retrieved_at = row.retrieved_at,
            relationship.source_uri = $source_uri,
            relationship.dataset_id = $dataset_id
        MERGE (subject:{entity_label} {{entity_id: trim(row.subject_id), run_id: $run_id}})
        ON CREATE SET subject.name = row.subject_label,
                      subject.source_uri = $source_uri,
                      subject.dataset_id = $dataset_id,
                      subject.retrieved_at = coalesce(row.retrieved_at, $ingested_at)
        MERGE (object:{entity_label} {{entity_id: trim(row.object_id), run_id: $run_id}})
        ON CREATE SET object.name = row.object_label,
                      object.entity_type = row.object_entity_type,
                      object.source_uri = $source_uri,
                      object.dataset_id = $dataset_id,
                      object.retrieved_at = coalesce(row.retrieved_at, $ingested_at)
        MERGE (relationship)-[has_subject:{subject_relationship}]->(subject)
        SET has_subject.run_id = $run_id,
            has_subject.source_uri = $source_uri,
            has_subject.retrieved_at = coalesce(row.retrieved_at, $ingested_at)
        MERGE (relationship)-[has_object:{object_relationship}]->(object)
        SET has_object.run_id = $run_id,
            has_object.source_uri = $source_uri,
            has_object.retrieved_at = coalesce(row.retrieved_at, $ingested_at)
        {asserted_in_clause}        {row_source_clause}""".format(
            relationship_label=_escape_cypher_identifier(
                graph_shape.relationship_label
            ),
            entity_label=_escape_cypher_identifier(graph_shape.entity_label),
            subject_relationship=_escape_cypher_identifier(
                graph_shape.subject_relationship
            ),
            object_relationship=_escape_cypher_identifier(
                graph_shape.object_relationship
            ),
            asserted_in_clause=asserted_in_clause,
            row_source_clause=row_source_clause,
        ),
        rows=rows,
        run_id=run_id,
        source_uri=source_uri,
        dataset_id=dataset_id,
        ingested_at=ingested_at,
    ).consume()


def _write_claims(
    session: Any,
    *,
    rows: list[dict[str, str]],
    run_id: str,
    source_uri: str,
    dataset_id: str,
    ingested_at: str,
    graph_shape: StructuredGraphShapeContract,
) -> None:
    asserted_in_clause = _asserted_in_clause(
        "claim",
        retrieved_at_expr="coalesce(row.retrieved_at, $ingested_at)",
        graph_shape=graph_shape,
    )
    row_source_clause = _row_source_clause(
        "claim",
        retrieved_at_expr="coalesce(row.retrieved_at, $ingested_at)",
        graph_shape=graph_shape,
    )
    session.run(
        """
        UNWIND $rows AS row
        MERGE (claim:{claim_label} {{claim_id: trim(row.claim_id), run_id: $run_id}})
        SET claim.claim_type = trim(row.claim_type),
            claim.subject_id = trim(row.subject_id),
            claim.subject_label = row.subject_label,
            claim.predicate_pid = row.predicate_pid,
            claim.predicate_label = row.predicate_label,
            claim.object_id = trim(row.object_id),
            claim.object_label = row.object_label,
            claim.value = row.value,
            claim.value_type = row.value_type,
            claim.claim_text = row.claim_text,
            claim.confidence = CASE
                WHEN coalesce(row.confidence, '') =~ '^[+-]?(\\d+\\.?\\d*|\\.\\d+)$' THEN toFloat(row.confidence)
                ELSE NULL
            END,
            claim.source = row.source,
            claim.source_url = row.source_url,
            claim.retrieved_at = row.retrieved_at,
            claim.source_row_id = trim(row.source_row_id),
            claim.source_uri = $source_uri,
            claim.dataset_id = $dataset_id
        MERGE (subject:{entity_label} {{entity_id: trim(row.subject_id), run_id: $run_id}})
        ON CREATE SET subject.name = row.subject_label,
                      subject.source_uri = $source_uri,
                      subject.dataset_id = $dataset_id,
                      subject.retrieved_at = coalesce(row.retrieved_at, $ingested_at)
        MERGE (claim)-[about:{about_relationship}]->(subject)
        SET about.run_id = $run_id,
            about.source_uri = $source_uri,
            about.retrieved_at = coalesce(row.retrieved_at, $ingested_at)
        FOREACH (_ IN CASE WHEN trim(coalesce(row.object_id, '')) = '' THEN [] ELSE [1] END |
            MERGE (object:{entity_label} {{entity_id: trim(row.object_id), run_id: $run_id}})
            ON CREATE SET object.name = row.object_label,
                          object.source_uri = $source_uri,
                          object.dataset_id = $dataset_id,
                          object.retrieved_at = coalesce(row.retrieved_at, $ingested_at)
            MERGE (claim)-[targets:{targets_relationship}]->(object)
            SET targets.run_id = $run_id,
                targets.source_uri = $source_uri,
                targets.retrieved_at = coalesce(row.retrieved_at, $ingested_at)
        )
        {asserted_in_clause}
        WITH claim, row
        OPTIONAL MATCH (fact:{fact_label} {{fact_id: trim(row.source_row_id), run_id: $run_id}})
        OPTIONAL MATCH (relationship:{relationship_label} {{rel_id: trim(row.source_row_id), run_id: $run_id}})
        FOREACH (_ IN CASE WHEN trim(row.claim_type) = 'fact' AND fact IS NOT NULL THEN [1] ELSE [] END |
            MERGE (claim)-[supported_by:{supported_by_relationship}]->(fact)
            SET supported_by.run_id = $run_id,
                supported_by.source_uri = $source_uri,
                supported_by.retrieved_at = coalesce(row.retrieved_at, $ingested_at),
                supported_by.source_row_id = trim(row.source_row_id)
        )
        FOREACH (_ IN CASE WHEN trim(row.claim_type) = 'relationship' AND relationship IS NOT NULL THEN [1] ELSE [] END |
            MERGE (claim)-[supported_by:{supported_by_relationship}]->(relationship)
            SET supported_by.run_id = $run_id,
                supported_by.source_uri = $source_uri,
                supported_by.retrieved_at = coalesce(row.retrieved_at, $ingested_at),
                supported_by.source_row_id = trim(row.source_row_id)
        )
        {row_source_clause}""".format(
            claim_label=_escape_cypher_identifier(graph_shape.claim_label),
            entity_label=_escape_cypher_identifier(graph_shape.entity_label),
            about_relationship=_escape_cypher_identifier(
                graph_shape.about_relationship
            ),
            targets_relationship=_escape_cypher_identifier(
                graph_shape.targets_relationship
            ),
            fact_label=_escape_cypher_identifier(graph_shape.fact_label),
            relationship_label=_escape_cypher_identifier(
                graph_shape.relationship_label
            ),
            supported_by_relationship=_escape_cypher_identifier(
                graph_shape.supported_by_relationship
            ),
            asserted_in_clause=asserted_in_clause,
            row_source_clause=row_source_clause,
        ),
        rows=rows,
        run_id=run_id,
        source_uri=source_uri,
        dataset_id=dataset_id,
        ingested_at=ingested_at,
    ).consume()


def write_structured_ingest_graph(
    session: Any,
    *,
    run_id: str,
    source_uri: str,
    dataset_id: str,
    ingested_at: str,
    entities_rows: list[dict[str, str]],
    facts_rows: list[dict[str, str]],
    relationship_rows: list[dict[str, str]],
    claims_rows: list[dict[str, str]],
    graph_shape: StructuredGraphShapeContract | None = None,
) -> None:
    resolved_graph_shape = (
        get_default_structured_graph_shape_contract()
        if graph_shape is None
        else graph_shape
    )
    _write_dataset_source(
        session,
        run_id=run_id,
        source_uri=source_uri,
        dataset_id=dataset_id,
        ingested_at=ingested_at,
        graph_shape=resolved_graph_shape,
    )
    _write_entities(
        session,
        rows=entities_rows,
        run_id=run_id,
        source_uri=source_uri,
        dataset_id=dataset_id,
        ingested_at=ingested_at,
        graph_shape=resolved_graph_shape,
    )
    _write_facts(
        session,
        rows=facts_rows,
        run_id=run_id,
        source_uri=source_uri,
        dataset_id=dataset_id,
        ingested_at=ingested_at,
        graph_shape=resolved_graph_shape,
    )
    _write_relationships(
        session,
        rows=relationship_rows,
        run_id=run_id,
        source_uri=source_uri,
        dataset_id=dataset_id,
        ingested_at=ingested_at,
        graph_shape=resolved_graph_shape,
    )
    _write_claims(
        session,
        rows=claims_rows,
        run_id=run_id,
        source_uri=source_uri,
        dataset_id=dataset_id,
        ingested_at=ingested_at,
        graph_shape=resolved_graph_shape,
    )


__all__ = ["write_structured_ingest_graph"]