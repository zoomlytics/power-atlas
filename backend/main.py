"""
Power Atlas Backend - FastAPI application with Apache AGE integration
"""
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Dict, Any, Optional
from contextlib import asynccontextmanager
import logging
import os
from age_helper import AGEHelper

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Database connection configuration
DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql://postgres:postgres@postgres:5432/power_atlas"
)
GRAPH_NAME = os.getenv("GRAPH_NAME", "power_atlas_graph")

# Global AGE helper instance
age_helper: Optional[AGEHelper] = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Manage application lifespan - startup and shutdown"""
    global age_helper
    
    # Startup
    try:
        logger.info("Initializing Apache AGE connection...")
        age_helper = AGEHelper(DATABASE_URL, GRAPH_NAME)
        logger.info("Apache AGE connection initialized successfully")
    except Exception as e:
        logger.error(f"Failed to initialize Apache AGE: {e}")
        # Don't raise here to allow the app to start and show errors in health check
    
    yield
    
    # Shutdown
    if age_helper:
        age_helper.close()
        logger.info("Apache AGE connection closed")


# Create FastAPI app with lifespan
app = FastAPI(
    title="Power Atlas API",
    description="Backend API for Power Atlas graph database",
    version="0.1.0",
    lifespan=lifespan
)

# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # In production, specify exact origins
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
    if age_helper is None:
        return {
            "status": "error",
            "message": "Database connection not initialized"
        }
    
    try:
        # Try a simple query to verify connection
        age_helper.execute_cypher("RETURN 1")
        return {"status": "ok", "message": "Backend and database are healthy"}
    except Exception as e:
        logger.error(f"Health check failed: {e}")
        return {
            "status": "error",
            "message": f"Database connection failed: {str(e)}"
        }


class CypherQuery(BaseModel):
    """Model for Cypher query request"""
    query: str
    params: Optional[Dict[str, Any]] = None


@app.post("/cypher")
async def execute_cypher(cypher_query: CypherQuery) -> Dict[str, Any]:
    """
    Execute a Cypher query via Apache AGE
    
    Args:
        cypher_query: CypherQuery model with query and optional params
        
    Returns:
        Dictionary with results or error
    """
    if age_helper is None:
        raise HTTPException(
            status_code=500,
            detail="Database connection not initialized"
        )
    
    try:
        results = age_helper.execute_cypher(
            cypher_query.query,
            cypher_query.params
        )
        return {
            "status": "success",
            "results": results,
            "count": len(results)
        }
    except Exception as e:
        logger.error(f"Error executing Cypher query: {e}")
        raise HTTPException(
            status_code=400,
            detail=f"Query execution failed: {str(e)}"
        )


@app.post("/seed")
async def seed_graph() -> Dict[str, Any]:
    """
    Seed the graph database with demo data
    
    Returns:
        Dictionary with status
    """
    if age_helper is None:
        raise HTTPException(
            status_code=500,
            detail="Database connection not initialized"
        )
    
    try:
        result = age_helper.seed_demo_graph()
        return result
    except Exception as e:
        logger.error(f"Error seeding graph: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Seeding failed: {str(e)}"
        )


@app.get("/")
async def root() -> Dict[str, str]:
    """Root endpoint"""
    return {
        "message": "Power Atlas API",
        "version": "0.1.0",
        "docs": "/docs"
    }
