"""
TechAdmin FastAPI Main Entry Point
Author: Roshan
Purpose: Initialize and run the FastAPI application
"""

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
from loguru import logger
import os

from App.apis.routes import router as api_router
from App.utils.config import Config, Logger


# Setup logging
Logger.setup()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    FastAPI lifespan context manager.
    Handles startup and shutdown events.
    
    TODO: Initialize services on startup
    - Connect to Ollama
    - Initialize LLM models
    - Setup database connections
    - Validate configuration
    """
    logger.info("Starting TechAdmin Agent Platform...")
    
    # Startup
    if not Config.validate():
        logger.error("Configuration validation failed")
        raise RuntimeError("Invalid configuration")
    
    logger.info(f"Config - Ollama: {Config.OLLAMA_HOST}, Model: {Config.MODEL_NAME}")
    
    yield
    
    # Shutdown
    logger.info("Shutting down TechAdmin Agent Platform...")


# Initialize FastAPI app
app = FastAPI(
    title="TechAdmin Agent Platform",
    description="AI-powered IT automation for password resets, account unlocks, and provisioning",
    version="1.0.0",
    lifespan=lifespan
)


# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # TODO: Restrict in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Include API routes
app.include_router(api_router)


@app.get("/", tags=["root"])
async def root():
    """Root endpoint."""
    return {
        "service": "TechAdmin Agent Platform",
        "version": "1.0.0",
        "status": "running",
        "docs": "/docs"
    }


if __name__ == "__main__":
    import uvicorn
    
    logger.info(f"Starting server on {Config.API_HOST}:{Config.API_PORT}")
    
    uvicorn.run(
        "App.main:app",
        host=Config.API_HOST,
        port=Config.API_PORT,
        reload=True,  # TODO: Set to False in production
        log_level=Config.LOG_LEVEL.lower()
    )
