"""FastAPI application entry point."""

from contextlib import asynccontextmanager

from contextlib import asynccontextmanager
from pathlib import Path

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app import __version__
from app.api.routes import config, health, jobs
from app.core.config import get_settings
from app.core.logging import setup_logging


@asynccontextmanager
async def lifespan(app: FastAPI):
    setup_logging()
    settings = get_settings()
    settings.upload_dir.mkdir(parents=True, exist_ok=True)
    settings.output_dir.mkdir(parents=True, exist_ok=True)
    settings.temp_dir.mkdir(parents=True, exist_ok=True)
    yield


app = FastAPI(
    title="RetainPDF Server",
    description="Backend API service for RetainPDF: OCR, translate, and render PDFs while preserving layout.",
    version=__version__,
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health.router)
app.include_router(jobs.router)
app.include_router(config.router)

# Serve frontend static files
static_dir = Path(__file__).resolve().parents[1] / "static"
if static_dir.exists():
    @app.get("/")
    async def serve_index():
        return FileResponse(static_dir / "index.html")

    app.mount("/", StaticFiles(directory=str(static_dir)), name="static")

if __name__ == "__main__":
    import uvicorn

    settings = get_settings()
    uvicorn.run(
        "app.main:app",
        host=settings.server_host,
        port=settings.server_port,
        reload=False,
        access_log=False,
    )
