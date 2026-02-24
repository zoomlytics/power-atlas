"""
Power Atlas Backend - FastAPI application
"""
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from typing import Dict
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

@app.get("/graph/status")
async def graph_status() -> Dict[str, str]:
    """
    Placeholder endpoint for future graph integration.
    
    Returns:
        Dictionary with graph integration status
    """
    raise HTTPException(
        status_code=503,
        detail="Graph integration is not configured yet"
    )


@app.get("/")
async def root() -> Dict[str, str]:
    """Root endpoint"""
    return {
        "message": "Power Atlas API",
        "version": "0.1.0",
        "docs": "/docs"
    }
