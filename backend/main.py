"""
Power Atlas Backend - FastAPI application
"""
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Dict, Any, Optional
import logging

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Create FastAPI app
app = FastAPI(
    title="Power Atlas API",
    description="Backend API for Power Atlas",
    version="0.1.0",
)

# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],  # Restrict to frontend origin for security
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
async def health_check() -> Dict[str, str]:
    """
    Health check endpoint
    
    Returns:
        Dictionary with status
    """
    return {"status": "ok", "message": "Backend is healthy"}


class CypherQuery(BaseModel):
    """Model for Cypher query request"""
    query: str
    params: Optional[Dict[str, Any]] = None


@app.post("/cypher")
async def execute_cypher(cypher_query: CypherQuery) -> Dict[str, Any]:
    """
    Execute a Cypher query.
    Note: Graph query service is currently not configured.
    
    Args:
        cypher_query: CypherQuery model with query and optional params
        
    Returns:
        Dictionary with results or error
    """
    raise HTTPException(
        status_code=503,
        detail="Graph query service is not configured"
    )


@app.post("/seed")
async def seed_graph() -> Dict[str, Any]:
    """
    Seed the graph database with demo data.
    Note: Graph seed service is currently not configured.
    
    Returns:
        Dictionary with status
    """
    raise HTTPException(
        status_code=503,
        detail="Graph seed service is not configured"
    )


@app.get("/")
async def root() -> Dict[str, str]:
    """Root endpoint"""
    return {
        "message": "Power Atlas API",
        "version": "0.1.0",
        "docs": "/docs"
    }
