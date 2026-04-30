from __future__ import annotations

from typing import Dict

from fastapi import APIRouter


backend_router = APIRouter()


@backend_router.get("/health")
async def health_check() -> Dict[str, str]:
    return {"status": "ok", "message": "Backend is healthy"}


@backend_router.get(
    "/graph/status",
    status_code=503,
    responses={
        503: {
            "description": "Graph integration is not configured yet",
            "content": {
                "application/json": {
                    "schema": {
                        "type": "object",
                        "properties": {"detail": {"type": "string"}},
                        "required": ["detail"],
                    },
                    "example": {"detail": "Graph integration is not configured yet"},
                }
            },
        }
    },
)
async def graph_status() -> Dict[str, str]:
    return {"detail": "Graph integration is not configured yet"}


@backend_router.get("/")
async def root() -> Dict[str, str]:
    return {
        "message": "Power Atlas API",
        "version": "0.1.0",
        "docs": "/docs",
    }


__all__ = ["backend_router"]