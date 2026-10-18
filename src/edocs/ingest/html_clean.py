"""
HTML decoding, cleaning, and structured Markdown conversion.

Preserves notes, warnings, steps, code indentation, and tables.
Removes navigation chrome, scripts, and copyright footers.
"""

from __future__ import annotations

import re
import unicodedata
from typing import Tuple, List
from bs4 import BeautifulSoup, NavigableString, Tag
import charset_normalizer


def decode_html(raw: bytes) -> str:
    """
    Robustly decode raw bytes to string.
    Tries charset declaration, BOM, charset-normalizer, then cp1252 fallback.
    """
    # 1. Check for UTF-8 BOM
    if raw.startswith(b"\xef\xbb\xbf"):
        return raw[3:].decode("utf-8", errors="replace")

    # 2. Check meta charset in the first 2048 bytes
    head = raw[:2048].decode("ascii", errors="ignore")
    m = re.search(r'''<meta[^>]+(?:charset=["']?([a-zA-Z0-9_-]+)|content=["'][^"']*charset=([a-zA-Z0-9_-]+))''', head, re.I)
    if m:
        encoding = m.group(1) or m.group(2)
        try:
            return raw.decode(encoding, errors="replace")
        except (LookupError, UnicodeDecodeError):
            pass

    # 3. Charset normalizer detection
    match = charset_normalizer.from_bytes(raw).best()
    if match and match.encoding:
        try:
            return raw.decode(match.encoding, errors="replace")
        except UnicodeDecodeError:
            pass

    # 4. Fallback cp1252 (very common for legacy Windows CHM files)
    return raw.decode("cp1252", errors="replace")


def _clean_table_to_markdown(table: Tag) -> str:
    """Convert an HTML table tag into a Markdown table or row-cards if > 8 columns."""
    rows = table.find_all("tr")
    if not rows:
        return ""

    grid: list[list[str]] = []
    for row in rows:
        cells = row.find_all(["th", "td"])
        row_vals = [re.sub(r"\s+", " ", c.get_text(" ")).strip().replace("|", "\\|") for c in cells]
        if any(row_vals):
            grid.append(row_vals)

    if not grid:
        return ""

    num_cols = max(len(r) for r in grid)
    # Pad shorter rows
    for r in grid:
        while len(r) < num_cols:
            r.append("")

    # If table is very wide (> 8 columns), convert to row cards
    if num_cols > 8:
        headers = grid[0]
        cards: list[str] = []
        for row_idx, r in enumerate(grid[1:], 1):
            card_lines = [f"**Row {row_idx}:**"]
            for col_idx, val in enumerate(r):
                col_name = headers[col_idx] if col_idx < len(headers) and headers[col_idx] else f"Col {col_idx+1}"
                card_lines.append(f"- **{col_name}:** {val}")
            cards.append("\n".join(card_lines))
        return "\n\n" + "\n\n".join(cards) + "\n\n"

    # Standard Markdown table
    header = grid[0]
    separator = ["---"] * num_cols
    lines = [
        "| " + " | ".join(header) + " |",
        "| " + " | ".join(separator) + " |",
    ]
    for r in grid[1:]:
        lines.append("| " + " | ".join(r) + " |")

    return "\n\n" + "\n".join(lines) + "\n\n"


def html_to_markdown(soup: BeautifulSoup, page_title: str = "") -> Tuple[str, List[str]]:
    """
    Convert a cleaned BeautifulSoup DOM tree to structured Markdown.
    Returns (markdown_text, image_list).
    """
    images: list[str] = []

    # 1. Remove unwanted elements
    for el in soup.find_all(["script", "style", "noscript", "iframe"]):
        el.decompose()

    # Remove navigation chrome and footers based on common classes
    unwanted_classes = re.compile(
        r"copyright|navigation|nav_bar|breadcrumbs|header_nav|footer_nav|print_button|symTblToc",
        re.I
    )
    for el in soup.find_all(class_=unwanted_classes):
        el.decompose()

    # Collect images and convert them to inline tags
    for img in soup.find_all("img"):
        src = img.get("src", "").strip()
        alt = img.get("alt", "").strip() or img.get("title", "").strip() or (src.split("/")[-1] if src else "image")
        if src:
            images.append(src)
        img.replace_with(f" [Image: {alt}] ")

    # Handle admonitions / notes / cautions / important / tips
    admonition_classes = {
        "note": "Note",
        "notetitle": "Note",
        "important": "Important",
        "importanttitle": "Important",
        "caution": "Caution",
        "cautiontitle": "Caution",
        "warning": "Warning",
        "tip": "Tip",
        "tiptitle": "Tip",
    }
    for el in soup.find_all(class_=list(admonition_classes.keys())):
        matched_class = next(c for c in el.get("class", []) if c.lower() in admonition_classes)
        label = admonition_classes[matched_class.lower()]
        text = re.sub(r"\s+", " ", el.get_text(" ")).strip()
        # Clean label prefix if already present in text
        text = re.sub(rf"^(?:{label}:?)\s*", "", text, flags=re.I)
        el.replace_with(f"\n\n> **{label}:** {text}\n\n")

    # Handle tables
    for table in soup.find_all("table"):
        md_table = _clean_table_to_markdown(table)
        table.replace_with(md_table)

    # Handle code blocks (<pre>)
    for pre in soup.find_all("pre"):
        code_text = pre.get_text()
        pre.replace_with(f"\n\n```\n{code_text}\n```\n\n")

    # Handle definition lists (<dl>)
    for dl in soup.find_all("dl"):
        dl_lines: list[str] = []
        for dt in dl.find_all("dt"):
            term = re.sub(r"\s+", " ", dt.get_text(" ")).strip()
            dd = dt.find_next_sibling("dd")
            defn = re.sub(r"\s+", " ", dd.get_text(" ")).strip() if dd else ""
            dl_lines.append(f"**{term}**: {defn}")
        dl.replace_with("\n\n" + "\n\n".join(dl_lines) + "\n\n")

    # Handle ordered lists (procedures / steps)
    for ol in soup.find_all("ol"):
        steps: list[str] = []
        for idx, li in enumerate(ol.find_all("li", recursive=False), 1):
            step_text = re.sub(r"\s+", " ", li.get_text(" ")).strip()
            steps.append(f"{idx}. {step_text}")
        ol.replace_with("\n\n" + "\n".join(steps) + "\n\n")

    # Handle unordered lists
    for ul in soup.find_all("ul"):
        bullets: list[str] = []
        for li in ul.find_all("li", recursive=False):
            bullet_text = re.sub(r"\s+", " ", li.get_text(" ")).strip()
            bullets.append(f"- {bullet_text}")
        ul.replace_with("\n\n" + "\n".join(bullets) + "\n\n")

    # Handle headings
    for h in soup.find_all(["h1", "h2", "h3", "h4", "h5", "h6"]):
        level = int(h.name[1])
        prefix = "#" * level
        text = re.sub(r"\s+", " ", h.get_text(" ")).strip()
        h.replace_with(f"\n\n{prefix} {text}\n\n")

    # Process paragraphs
    for p in soup.find_all("p"):
        p_text = re.sub(r"\s+", " ", p.get_text(" ")).strip()
        if p_text:
            p.replace_with(f"\n\n{p_text}\n\n")

    raw_text = soup.get_text("\n")
    
    # Normalize unicode (NFKC) while keeping identifiers and newlines intact
    clean_lines = []
    for line in raw_text.splitlines():
        line_stripped = line.rstrip()
        clean_lines.append(unicodedata.normalize("NFKC", line_stripped))

    result = re.sub(r"\n{3,}", "\n\n", "\n".join(clean_lines)).strip()
    return result, images
