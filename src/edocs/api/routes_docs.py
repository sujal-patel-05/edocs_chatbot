"""
Document and image viewer API routes.

Serves sanitised original HTML topics and extracted images.
"""

from __future__ import annotations

import re
from pathlib import Path
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import HTMLResponse, FileResponse
from bs4 import BeautifulSoup
from src.edocs.api.auth import get_current_user

router = APIRouter(prefix="/api/v1", tags=["Docs"])
EXTRACTED_DIR = Path("data/extracted/edocs").resolve()


def _sanitize_html(html: str, doc_dir: str) -> str:
    """Sanitize HTML: remove scripts, rewrite image links to viewer API, add styling."""
    try:
        import nh3
        # First-pass sanitisation with nh3
        cleaned = nh3.clean(
            html,
            tags={"p", "h1", "h2", "h3", "h4", "h5", "h6", "b", "i", "strong", "em", "a", "img", "table", "tr", "th", "td", "ul", "ol", "li", "dl", "dt", "dd", "pre", "code", "blockquote", "div", "span", "br", "hr"},
            attributes={
                "*": {"class", "id"},
                "a": {"href", "name", "target"},
                "img": {"src", "alt", "title", "width", "height"},
            },
        )
    except Exception:
        # Fallback to BeautifulSoup cleaning
        soup = BeautifulSoup(html, "lxml")
        for tag in soup.find_all(["script", "style", "iframe", "noscript"]):
            tag.decompose()
        cleaned = str(soup)

    # Rewrite image links to /api/v1/docs_raw/
    soup = BeautifulSoup(cleaned, "html.parser")
    for img in soup.find_all("img"):
        src = img.get("src", "")
        if src and not src.startswith(("http:", "https:", "/")):
            # Resolve relative to doc_dir
            rel_img = (Path(doc_dir) / src).as_posix().lstrip("/")
            img["src"] = f"/api/v1/docs_raw/{rel_img}"

    # Wrap in clean viewer layout
    viewer_html = f"""<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <title>eDocs Viewer</title>
    <style>
        body {{
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
            line-height: 1.6;
            color: #1e293b;
            padding: 24px;
            max-width: 900px;
            margin: 0 auto;
            background: #ffffff;
        }}
        h1, h2, h3, h4 {{ color: #0f172a; margin-top: 1.5em; }}
        table {{ border-collapse: collapse; width: 100%; margin: 16px 0; }}
        th, td {{ border: 1px solid #cbd5e1; padding: 8px 12px; text-align: left; }}
        th {{ background: #f1f5f9; font-weight: 600; }}
        pre, code {{ background: #f8fafc; border: 1px solid #e2e8f0; border-radius: 4px; font-family: monospace; }}
        pre {{ padding: 12px; overflow-x: auto; }}
        code {{ padding: 2px 4px; }}
        blockquote, .note, .important, .caution {{
            border-left: 4px solid #3b82f6;
            background: #eff6ff;
            padding: 8px 16px;
            margin: 16px 0;
            border-radius: 0 4px 4px 0;
        }}
        .caution {{ border-left-color: #ef4444; background: #fef2f2; }}
        .important {{ border-left-color: #f59e0b; background: #fffbeb; }}
        img {{ max-width: 100%; height: auto; border: 1px solid #e2e8f0; border-radius: 4px; margin: 8px 0; }}
    </style>
</head>
<body>
    {str(soup)}
</body>
</html>"""
    return viewer_html


@router.get("/docs/{doc_id:path}", response_class=HTMLResponse)
def get_document(doc_id: str, anchor: str = "", user: str = Depends(get_current_user)):
    """Serve sanitized original topic HTML."""
    clean_id = doc_id.removeprefix("edocs/").replace("\\", "/")
    file_path = EXTRACTED_DIR / clean_id

    if not file_path.exists() or not file_path.is_file():
        raise HTTPException(status_code=404, detail=f"Topic {doc_id} not found.")

    raw = file_path.read_bytes()
    try:
        html = raw.decode("utf-8")
    except UnicodeDecodeError:
        html = raw.decode("cp1252", errors="replace")

    doc_dir = str(file_path.parent.relative_to(EXTRACTED_DIR)).replace("\\", "/")
    if doc_dir == ".":
        doc_dir = ""

    sanitized = _sanitize_html(html, doc_dir)
    return HTMLResponse(content=sanitized)


@router.get("/docs_raw/{raw_path:path}")
def get_raw_file(raw_path: str, user: str = Depends(get_current_user)):
    """Serve original image files."""
    clean_path = raw_path.removeprefix("edocs/").replace("\\", "/")
    file_path = EXTRACTED_DIR / clean_path

    if not file_path.exists() or not file_path.is_file():
        raise HTTPException(status_code=404, detail="File not found.")

    return FileResponse(file_path)
