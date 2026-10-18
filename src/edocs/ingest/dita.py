"""
DITA structure and metadata extractor.

Extracts topic type, short description/summary, and product area from DITA-generated HTML.
"""

from __future__ import annotations

import re
from typing import Optional
from bs4 import BeautifulSoup

CATEGORY_MAP = {
    "concept": "concept",
    "reference": "reference",
    "task": "task",
    "troubleshooting": "troubleshooting",
    "records and fields": "reference",
    "parameters": "reference",
    "poweron lexicon": "reference",
    "reports": "reference",
    "specfiles": "reference",
    "video": "concept",
    "topic": "concept",
}


def detect_topic_type(soup: BeautifulSoup) -> str:
    """
    Detect DITA topic type from ZOOMCATEGORY meta tag, DC.Type meta tag,
    or structural inspection.
    """
    # 1. Check ZOOMCATEGORY meta tag (found consistently in Symitar eDocs)
    for meta in soup.find_all("meta"):
        if meta.get("name", "").upper() == "ZOOMCATEGORY":
            content = meta.get("content", "").strip().lower()
            if content in CATEGORY_MAP:
                return CATEGORY_MAP[content]

    # 2. Check DC.Type meta tag
    dc_type = soup.find("meta", attrs={"name": re.compile(r"^dc\.type$", re.I)})
    if dc_type and dc_type.get("content"):
        ctype = dc_type["content"].strip().lower()
        if ctype in CATEGORY_MAP:
            return CATEGORY_MAP[ctype]

    # 3. Structural inspection fallback
    if soup.find("ol", class_=re.compile(r"steps|task", re.I)):
        return "task"
    if soup.find("table") and len(soup.find_all("table")) >= 2:
        return "reference"

    return "concept"


def extract_summary(soup: BeautifulSoup) -> Optional[str]:
    """
    Extract the short description / summary of the topic.
    Looks for meta abstract, .shortDesc paragraph, or first clean paragraph.
    """
    # Check meta abstract
    meta = soup.find("meta", attrs={"name": re.compile(r"abstract|description", re.I)})
    if meta and meta.get("content"):
        return meta["content"].strip()

    # Check shortDesc class
    p_desc = soup.find(["p", "div"], class_=re.compile(r"shortdesc", re.I))
    if p_desc:
        text = re.sub(r"\s+", " ", p_desc.get_text(" ")).strip()
        if text:
            return text

    # First paragraph with reasonable text
    for p in soup.find_all("p"):
        # Ignore empty or header paragraphs
        text = re.sub(r"\s+", " ", p.get_text(" ")).strip()
        if len(text) > 25 and not p.find_parent("table"):
            return text

    return None
