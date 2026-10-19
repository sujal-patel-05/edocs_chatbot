"""
FastAPI application entrypoint for Symitar eDocs Assistant.
"""

from __future__ import annotations

from pathlib import Path
import gzip
import shutil


def ensure_database():
    db_path = Path("data/edocs.db")
    gz_path = Path("data/edocs.db.gz")
    if gz_path.exists() and (not db_path.exists() or db_path.stat().st_size < 10000000):
        db_path.parent.mkdir(parents=True, exist_ok=True)
        with gzip.open(gz_path, "rb") as f_in, open(db_path, "wb") as f_out:
            shutil.copyfileobj(f_in, f_out)


ensure_database()

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from src.edocs.api.routes_chat import router as chat_router
from src.edocs.api.routes_docs import router as docs_router
from src.edocs.api.routes_fields import router as fields_router
from src.edocs.config import load_settings

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
    chunks = 0
    fields = 0
    try:
        import sqlite3
        with sqlite3.connect("data/edocs.db") as conn:
            chunks = conn.execute("SELECT count(*) FROM chunks").fetchone()[0]
            fields = conn.execute("SELECT count(*) FROM fields").fetchone()[0]
    except Exception:
        pass
    return {
        "status": "ready",
        "default_release": settings.app.default_release,
        "llm_provider": settings.llm.provider,
        "chunks_indexed": chunks,
        "fields_indexed": fields,
    }


# Mount reference UI
web_dir = Path("web").resolve()
if (web_dir / "reference.html").exists():
    @app.get("/", include_in_schema=False)
    def index():
        return FileResponse(web_dir / "reference.html")

    app.mount("/web", StaticFiles(directory=str(web_dir)), name="web")
