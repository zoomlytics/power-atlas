from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from typing import Dict

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Power Atlas API starting up")
    yield


def create_backend_app() -> FastAPI:
    app = FastAPI(
        title="Power Atlas API",
        description="Backend API for Power Atlas",
        version="0.1.0",
        lifespan=lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:3000"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.get("/health")
    async def health_check() -> Dict[str, str]:
        return {"status": "ok", "message": "Backend is healthy"}

    @app.get(
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

    @app.get("/")
    async def root() -> Dict[str, str]:
        return {
            "message": "Power Atlas API",
            "version": "0.1.0",
            "docs": "/docs",
        }

    return app


__all__ = ["create_backend_app"]