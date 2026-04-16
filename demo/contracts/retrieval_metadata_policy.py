"""Compatibility shim for retrieval metadata policy."""

from power_atlas.contracts.retrieval_metadata_policy import (
    FieldSurfacePolicy,
    RETRIEVAL_METADATA_SURFACE_POLICY,
    RetrievalMetadataSurface,
)

__all__ = [
    "FieldSurfacePolicy",
    "RetrievalMetadataSurface",
    "RETRIEVAL_METADATA_SURFACE_POLICY",
]
