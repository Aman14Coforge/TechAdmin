"""TechAdmin FastAPI application with embedded Ivanti scheduler."""
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from loguru import logger

from App.apis.routes import router as api_router
from App.apis.patch_routes import router as patch_router
from App.apis.patch_scheduler_routes import router as patch_scheduler_router
from App.services.patch.bootstrap import start_patch_background_services
from App.services.patch.scheduler import shutdown_patch_scheduler
from App.utils.config import Config, Logger

Logger.setup()

@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Starting TechAdmin Agent Platform...")
    if not Config.validate():
        raise RuntimeError("Invalid configuration")
    start_patch_background_services()
    yield
    shutdown_patch_scheduler()
    logger.info("Shutting down TechAdmin Agent Platform...")

app = FastAPI(
    title="TechAdmin Agent Platform",
    description="AI-powered identity automation and Ivanti patch compliance",
    version="1.2.0",
    lifespan=lifespan,
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(api_router)
app.include_router(patch_router)
app.include_router(patch_scheduler_router)

@app.get("/", tags=["root"])
async def root():
    return {"service": "TechAdmin Agent Platform", "version": "1.2.0", "status": "running", "docs": "/docs"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "App.main:app",
        host=Config.API_HOST,
        port=Config.API_PORT,
        reload=True,
        log_level=Config.LOG_LEVEL.lower(),
    )
