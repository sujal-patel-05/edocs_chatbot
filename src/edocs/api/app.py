"""
FastAPI application entrypoint for Symitar eDocs Assistant.
"""

from __future__ import annotations

from pathlib import Path
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from src.edocs.api.routes_chat import router as chat_router
from src.edocs.api.routes_docs import router as docs_router
from src.edocs.api.routes_fields import router as fields_router
from src.edocs.config import load_settings


def ensure_database():
    db_path = Path("data/edocs.db")
    gz_path = Path("data/edocs.db.gz")
    if not db_path.exists() and gz_path.exists():
        import gzip
        import shutil
        db_path.parent.mkdir(parents=True, exist_ok=True)
        with gzip.open(gz_path, "rb") as f_in, open(db_path, "wb") as f_out:
            shutil.copyfileobj(f_in, f_out)


ensure_database()

app = FastAPI(
    title="Symitar eDocs Assistant API",
    description="Internal documentation assistant API for Jack Henry Symitar Episys eDocs",
    version="1.0.0",
)

# CORS middleware for local dev UI
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount API routers
app.include_router(chat_router)
app.include_router(docs_router)
app.include_router(fields_router)


@app.get("/healthz", tags=["Health"])
def health_check():
    """Liveness probe: process is running."""
    return {"status": "ok"}


@app.get("/readyz", tags=["Health"])
def readiness_check():
    """Readiness probe: database and models configured."""
    settings = load_settings()
    return {
        "status": "ready",
        "default_release": settings.app.default_release,
        "llm_provider": settings.llm.provider,
    }


# Mount reference UI
web_dir = Path("web").resolve()
if (web_dir / "reference.html").exists():
    @app.get("/", include_in_schema=False)
    def index():
        return FileResponse(web_dir / "reference.html")

    app.mount("/web", StaticFiles(directory=str(web_dir)), name="web")
