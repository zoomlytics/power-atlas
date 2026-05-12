from __future__ import annotations

from pydantic import BaseModel, Field


class GraphStatusResponse(BaseModel):
    status: str
    detail: str
    neo4j_uri: str | None = None
    database: str | None = None


class GraphSummaryCountsResponse(BaseModel):
    document_count: int
    chunk_count: int
    claim_count: int
    mention_count: int
    cluster_count: int
    canonical_entity_count: int


class GraphSummaryResponse(BaseModel):
    status: str
    detail: str
    neo4j_uri: str | None = None
    database: str | None = None
    counts: GraphSummaryCountsResponse | None = None


class RunScopedGraphCountsRequestBody(BaseModel):
    run_id: str = Field(min_length=1)


class RunScopedGraphCountsResponseBody(BaseModel):
    chunk_count: int
    claim_count: int
    mention_count: int
    cluster_count: int


class RunScopedGraphCountsResponse(BaseModel):
    status: str
    detail: str
    run_id: str
    neo4j_uri: str
    database: str
    counts: RunScopedGraphCountsResponseBody | None = None


class GraphHealthSummaryRequestBody(BaseModel):
    run_id: str = Field(min_length=1)
    alignment_version: str | None = None


class GraphHealthParticipationSummaryResponse(BaseModel):
    total_edges: int
    edges_by_role: dict[str, int]
    total_claims: int
    claims_with_zero_edges: int
    claim_coverage_pct: float | None


class GraphHealthMentionSummaryResponse(BaseModel):
    total_mentions: int
    clustered_mentions: int
    unclustered_mentions: int
    unresolved_rate_pct: float | None


class GraphHealthAlignmentSummaryResponse(BaseModel):
    total_clusters: int
    aligned_clusters: int
    unaligned_clusters: int
    alignment_coverage_pct: float | None


class GraphHealthSummaryResponse(BaseModel):
    status: str
    detail: str
    run_id: str
    alignment_version: str | None
    neo4j_uri: str
    database: str
    participation_summary: GraphHealthParticipationSummaryResponse | None = None
    mention_summary: GraphHealthMentionSummaryResponse | None = None
    alignment_summary: GraphHealthAlignmentSummaryResponse | None = None


__all__ = [
    "GraphHealthAlignmentSummaryResponse",
    "GraphHealthMentionSummaryResponse",
    "GraphHealthParticipationSummaryResponse",
    "GraphHealthSummaryRequestBody",
    "GraphHealthSummaryResponse",
    "GraphSummaryCountsResponse",
    "GraphSummaryResponse",
    "GraphStatusResponse",
    "RunScopedGraphCountsRequestBody",
    "RunScopedGraphCountsResponse",
    "RunScopedGraphCountsResponseBody",
]