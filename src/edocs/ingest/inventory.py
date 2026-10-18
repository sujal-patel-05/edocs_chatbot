"""
Phase 1 — CHM Discovery Inventory Tool

Extracts and analyzes CHM files to produce a comprehensive inventory report.
This must run before any parser is finalized (spec section 8).

Usage:
    python -m src.edocs.ingest.inventory data/extracted/edocs --release 2023.00
"""

from __future__ import annotations

import hashlib
import json
import re
import sys
from collections import Counter, defaultdict
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

# Add project root to path
sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

try:
    from bs4 import BeautifulSoup
    from charset_normalizer import from_bytes
except ImportError as e:
    print(f"Missing dependency: {e}. Run: pip install beautifulsoup4 lxml charset-normalizer")
    sys.exit(1)

from src.edocs.ingest.chm_meta import load_system_from_dir
from src.edocs.ingest.sitemap import (
    Node,
    count_nodes,
    depth_histogram,
    load_sitemap,
    max_depth,
    walk,
)


# ────────────────────────────────────────────────────────
# Data classes for the report
# ────────────────────────────────────────────────────────

@dataclass
class FileStats:
    total_files: int = 0
    html_files: int = 0
    image_files: int = 0
    css_files: int = 0
    js_files: int = 0
    other_files: int = 0
    extensions: dict[str, int] = field(default_factory=dict)


@dataclass
class TOCStats:
    total_entries: int = 0
    entries_with_page: int = 0
    entries_without_page: int = 0
    max_depth: int = 0
    depth_histogram: dict[int, int] = field(default_factory=dict)
    orphan_pages: list[str] = field(default_factory=list)
    orphan_count: int = 0


@dataclass
class IndexStats:
    total_keywords: int = 0
    keywords_with_multiple_targets: int = 0
    sample_multi_target_keywords: list[dict[str, Any]] = field(default_factory=list)


@dataclass
class MetaStats:
    meta_names: dict[str, int] = field(default_factory=dict)
    dita_types_found: dict[str, int] = field(default_factory=dict)
    has_dc_type: bool = False
    has_dc_title: bool = False
    has_dc_identifier: bool = False
    has_abstract: bool = False
    has_keywords: bool = False
    zoom_categories: dict[str, int] = field(default_factory=dict)


@dataclass
class TableStats:
    total_tables: int = 0
    column_count_histogram: dict[int, int] = field(default_factory=dict)
    top_first_column_labels: list[tuple[str, int]] = field(default_factory=list)


@dataclass
class LinkStats:
    internal_links: int = 0
    cross_chm_links: int = 0
    external_links: int = 0
    javascript_links: int = 0
    anchor_only_links: int = 0
    broken_links: int = 0
    broken_link_samples: list[str] = field(default_factory=list)


@dataclass
class ContentStats:
    pages_with_script: int = 0
    pages_with_iframe: int = 0
    pages_with_hidden: int = 0
    pages_with_dynamic_content: int = 0
    script_sample_pages: list[str] = field(default_factory=list)


@dataclass
class DuplicateStats:
    total_unique_hashes: int = 0
    duplicate_groups: int = 0
    total_duplicate_pages: int = 0
    sample_duplicates: list[dict[str, Any]] = field(default_factory=list)


# ────────────────────────────────────────────────────────
# Encoding detection helper
# ────────────────────────────────────────────────────────

def detect_and_decode(raw: bytes) -> tuple[str, str]:
    """Decode bytes trying meta charset, BOM, charset-normalizer, fallback cp1252."""
    # Check for BOM
    if raw.startswith(b"\xef\xbb\xbf"):
        return raw[3:].decode("utf-8", errors="replace"), "utf-8-bom"

    # Try to find charset in meta tag
    head = raw[:2048].decode("ascii", errors="ignore").lower()
    charset_match = re.search(r'charset[="\s]+([a-zA-Z0-9_-]+)', head)
    if charset_match:
        charset = charset_match.group(1).strip('"\'')
        try:
            return raw.decode(charset, errors="replace"), charset
        except (UnicodeDecodeError, LookupError):
            pass

    # Try UTF-8
    try:
        decoded = raw.decode("utf-8")
        return decoded, "utf-8"
    except UnicodeDecodeError:
        pass

    # charset-normalizer
    result = from_bytes(raw)
    best = result.best()
    if best:
        return str(best), best.encoding

    # Fallback
    return raw.decode("cp1252", errors="replace"), "cp1252"


# ────────────────────────────────────────────────────────
# CSS class extraction
# ────────────────────────────────────────────────────────

TARGET_ELEMENTS = {"body", "div", "section", "table", "p", "pre", "span", "h1", "h2", "h3", "h4", "dl", "dt", "dd"}


def extract_css_classes(soup: BeautifulSoup) -> Counter:
    """Extract CSS class names from target elements."""
    classes: Counter = Counter()
    for elem in soup.find_all(TARGET_ELEMENTS):
        cls_list = elem.get("class", [])
        if isinstance(cls_list, list):
            for c in cls_list:
                classes[c] += 1
        elif isinstance(cls_list, str):
            classes[cls_list] += 1
    return classes


# ────────────────────────────────────────────────────────
# Main inventory function
# ────────────────────────────────────────────────────────

def run_inventory(extracted_dir: Path, release: str) -> dict[str, Any]:
    """Run full Phase 1 inventory on extracted CHM directory."""
    print(f"\n{'='*60}")
    print(f"Phase 1: CHM Discovery Inventory")
    print(f"Release: {release}")
    print(f"Source: {extracted_dir}")
    print(f"{'='*60}\n")

    report: dict[str, Any] = {
        "release": release,
        "source_dir": str(extracted_dir),
    }

    # ── 1. #SYSTEM metadata ──
    print("[1/11] Parsing #SYSTEM metadata...")
    system_meta = load_system_from_dir(extracted_dir)
    report["system_metadata"] = system_meta
    print(f"  Title: {system_meta.get('title', 'N/A')}")
    print(f"  Contents file: {system_meta.get('contents_file', 'N/A')}")
    print(f"  Index file: {system_meta.get('index_file', 'N/A')}")
    print(f"  Default topic: {system_meta.get('default_topic', 'N/A')}")

    # ── 2. File statistics ──
    print("\n[2/11] Counting files by type...")
    file_stats = FileStats()
    all_files = list(extracted_dir.rglob("*"))
    all_files = [f for f in all_files if f.is_file()]
    file_stats.total_files = len(all_files)

    # Filter out internal CHM files
    internal_prefixes = ("#", "$", "::")
    content_files = [f for f in all_files if not any(f.name.startswith(p) for p in internal_prefixes)]

    ext_counter: Counter = Counter()
    html_paths: list[Path] = []

    for f in content_files:
        ext = f.suffix.lower()
        ext_counter[ext] += 1
        if ext in (".html", ".htm"):
            html_paths.append(f)
            file_stats.html_files += 1
        elif ext in (".gif", ".png", ".jpg", ".jpeg", ".bmp", ".svg"):
            file_stats.image_files += 1
        elif ext == ".css":
            file_stats.css_files += 1
        elif ext == ".js":
            file_stats.js_files += 1
        else:
            file_stats.other_files += 1

    file_stats.extensions = dict(ext_counter.most_common())
    report["file_stats"] = asdict(file_stats)
    print(f"  Total: {file_stats.total_files}, HTML: {file_stats.html_files}, "
          f"Images: {file_stats.image_files}")

    # ── 3. TOC parsing ──
    print("\n[3/11] Parsing table of contents (.hhc)...")
    toc_stats = TOCStats()
    toc_pages: set[str] = set()
    toc_root = None

    contents_file = system_meta.get("contents_file", "")
    hhc_path = extracted_dir / contents_file if contents_file else None
    if hhc_path and hhc_path.exists():
        toc_root = load_sitemap(hhc_path)
        toc_stats.total_entries = count_nodes(toc_root)
        toc_stats.max_depth = max_depth(toc_root)
        toc_stats.depth_histogram = depth_histogram(toc_root)

        for path, node in walk(toc_root):
            if node.locals:
                toc_stats.entries_with_page += 1
                for loc in node.locals:
                    # Normalize path
                    normalized = loc.replace("\\", "/").split("#")[0].lower()
                    toc_pages.add(normalized)
            else:
                toc_stats.entries_without_page += 1

        # Find orphan pages (HTML files not in TOC)
        for hp in html_paths:
            rel = str(hp.relative_to(extracted_dir)).replace("\\", "/").lower()
            if rel not in toc_pages:
                toc_stats.orphan_pages.append(rel)

        toc_stats.orphan_count = len(toc_stats.orphan_pages)

    report["toc_stats"] = {
        "total_entries": toc_stats.total_entries,
        "entries_with_page": toc_stats.entries_with_page,
        "entries_without_page": toc_stats.entries_without_page,
        "max_depth": toc_stats.max_depth,
        "depth_histogram": toc_stats.depth_histogram,
        "orphan_count": toc_stats.orphan_count,
        "orphan_sample": toc_stats.orphan_pages[:20],
    }
    print(f"  TOC entries: {toc_stats.total_entries} "
          f"(with page: {toc_stats.entries_with_page}, "
          f"without: {toc_stats.entries_without_page})")
    print(f"  Max depth: {toc_stats.max_depth}")
    print(f"  Orphan pages (not in TOC): {toc_stats.orphan_count}")

    # ── 4. Keyword index (.hhk) ──
    print("\n[4/11] Parsing keyword index (.hhk)...")
    index_stats = IndexStats()
    index_file = system_meta.get("index_file", "")

    # Look for .hhk files - they may be under $WWKeywordLinks
    hhk_path = None
    if index_file:
        candidate = extracted_dir / index_file
        if candidate.exists():
            hhk_path = candidate
    if not hhk_path:
        hhk_files = list(extracted_dir.rglob("*.hhk"))
        if hhk_files:
            hhk_path = hhk_files[0]

    if hhk_path and hhk_path.exists():
        idx_root = load_sitemap(hhk_path)
        for path, node in walk(idx_root):
            index_stats.total_keywords += 1
            if len(node.locals) > 1:
                index_stats.keywords_with_multiple_targets += 1
                if len(index_stats.sample_multi_target_keywords) < 10:
                    index_stats.sample_multi_target_keywords.append({
                        "keyword": node.name,
                        "targets": node.locals[:5],
                    })
    else:
        print("  No .hhk index file found")

    report["index_stats"] = asdict(index_stats)
    print(f"  Keywords: {index_stats.total_keywords}, "
          f"Multi-target: {index_stats.keywords_with_multiple_targets}")

    # ── 5–11. Analyze HTML pages ──
    print(f"\n[5/11] Analyzing {len(html_paths)} HTML pages...")
    meta_stats = MetaStats()
    table_stats = TableStats()
    link_stats = LinkStats()
    content_stats = ContentStats()

    all_css_classes: Counter = Counter()
    first_col_labels: Counter = Counter()
    encoding_counter: Counter = Counter()
    content_hashes: defaultdict[str, list[str]] = defaultdict(list)

    # Topic type samples
    topic_type_samples: defaultdict[str, list[str]] = defaultdict(list)

    total = len(html_paths)
    for i, hp in enumerate(html_paths):
        if (i + 1) % 500 == 0 or i == 0:
            print(f"  Processing page {i+1}/{total}...")

        rel_path = str(hp.relative_to(extracted_dir)).replace("\\", "/")

        try:
            raw = hp.read_bytes()
        except Exception:
            continue

        text, encoding = detect_and_decode(raw)
        encoding_counter[encoding] += 1

        # Content hash for dedup
        normalized_text = re.sub(r"\s+", " ", text).strip().lower()
        text_hash = hashlib.sha256(normalized_text.encode("utf-8")).hexdigest()[:16]
        content_hashes[text_hash].append(rel_path)

        try:
            soup = BeautifulSoup(text, "lxml")
        except Exception:
            try:
                soup = BeautifulSoup(text, "html.parser")
            except Exception:
                continue

        # Meta tags
        for meta in soup.find_all("meta"):
            name = (meta.get("name") or "").strip()
            if name:
                meta_stats.meta_names[name] = meta_stats.meta_names.get(name, 0) + 1
                name_lower = name.lower()
                if name_lower == "dc.type":
                    meta_stats.has_dc_type = True
                    content = (meta.get("content") or "").strip()
                    if content:
                        meta_stats.dita_types_found[content] = meta_stats.dita_types_found.get(content, 0) + 1
                elif name_lower == "dc.title":
                    meta_stats.has_dc_title = True
                elif name_lower == "dc.identifier":
                    meta_stats.has_dc_identifier = True
                elif name_lower == "abstract":
                    meta_stats.has_abstract = True
                elif name_lower == "keywords":
                    meta_stats.has_keywords = True
                elif name_lower == "zoomcategory":
                    content = (meta.get("content") or "").strip()
                    if content:
                        meta_stats.zoom_categories[content] = meta_stats.zoom_categories.get(content, 0) + 1

                        # Collect topic type samples
                        if len(topic_type_samples[content]) < 10:
                            topic_type_samples[content].append(rel_path)

        # CSS classes
        page_classes = extract_css_classes(soup)
        all_css_classes.update(page_classes)

        # Tables
        tables = soup.find_all("table")
        table_stats.total_tables += len(tables)
        for tbl in tables:
            rows = tbl.find_all("tr")
            if rows:
                cols = len(rows[0].find_all(["th", "td"]))
                table_stats.column_count_histogram[cols] = (
                    table_stats.column_count_histogram.get(cols, 0) + 1
                )
                # First column labels
                for row in rows:
                    cells = row.find_all(["th", "td"])
                    if len(cells) >= 2:
                        label = re.sub(r"\s+", " ", cells[0].get_text(" ")).strip()
                        if label and len(label) < 80:
                            first_col_labels[label] += 1

        # Links
        for a in soup.find_all("a", href=True):
            href = a["href"].strip()
            href_lower = href.lower()
            if href_lower.startswith(("http:", "https:")):
                link_stats.external_links += 1
            elif href_lower.startswith("javascript:"):
                link_stats.javascript_links += 1
            elif href_lower.startswith(("ms-its:", "mk:@msitstore:", "its:")):
                link_stats.cross_chm_links += 1
            elif href.startswith("#"):
                link_stats.anchor_only_links += 1
            else:
                link_stats.internal_links += 1

        # Script, iframe, hidden content
        scripts = soup.find_all("script")
        if scripts:
            # Filter out the standard preload script
            non_standard = [s for s in scripts if s.string and "preload" not in (s.string or "")
                           and "tofTog" not in (s.string or "")
                           and "initTof" not in (s.string or "")]
            if non_standard:
                content_stats.pages_with_script += 1
                if len(content_stats.script_sample_pages) < 10:
                    content_stats.script_sample_pages.append(rel_path)

        if soup.find_all("iframe"):
            content_stats.pages_with_iframe += 1

        # Hidden content
        hidden = soup.find_all(style=re.compile(r"display\s*:\s*none", re.I))
        hidden += soup.find_all(attrs={"hidden": True})
        if hidden:
            content_stats.pages_with_hidden += 1

    # Finalize stats
    table_stats.top_first_column_labels = first_col_labels.most_common(100)

    report["meta_stats"] = asdict(meta_stats)
    report["css_classes_top_50"] = dict(all_css_classes.most_common(50))
    report["table_stats"] = {
        "total_tables": table_stats.total_tables,
        "column_count_histogram": table_stats.column_count_histogram,
        "top_first_column_labels": [
            {"label": label, "count": count}
            for label, count in table_stats.top_first_column_labels
        ],
    }
    report["link_stats"] = asdict(link_stats)
    report["content_stats"] = asdict(content_stats)
    report["encoding_stats"] = dict(encoding_counter.most_common())

    # Duplicate analysis
    print("\n[9/11] Analyzing duplicates...")
    dup_stats = DuplicateStats()
    dup_stats.total_unique_hashes = len(content_hashes)
    for h, paths in content_hashes.items():
        if len(paths) > 1:
            dup_stats.duplicate_groups += 1
            dup_stats.total_duplicate_pages += len(paths) - 1
            if len(dup_stats.sample_duplicates) < 10:
                dup_stats.sample_duplicates.append({
                    "hash": h,
                    "count": len(paths),
                    "pages": paths[:5],
                })

    report["duplicate_stats"] = asdict(dup_stats)
    print(f"  Unique content hashes: {dup_stats.total_unique_hashes}")
    print(f"  Duplicate groups: {dup_stats.duplicate_groups}")
    print(f"  Total duplicate pages: {dup_stats.total_duplicate_pages}")

    # Topic type samples
    print("\n[10/11] Collecting topic type samples...")
    report["topic_type_samples"] = {
        k: v for k, v in topic_type_samples.items()
    }

    # Save sample pages
    print("\n[11/11] Saving sample pages...")
    samples_dir = Path("data/reports/samples")
    samples_dir.mkdir(parents=True, exist_ok=True)
    for topic_type, sample_paths in topic_type_samples.items():
        for sp in sample_paths[:3]:
            src = extracted_dir / sp
            if src.exists():
                safe_name = re.sub(r"[^\w.]", "_", sp)
                dest = samples_dir / f"{topic_type}_{safe_name}"
                try:
                    dest.write_bytes(src.read_bytes())
                except Exception:
                    pass

    # Summary
    print(f"\n{'='*60}")
    print(f"INVENTORY SUMMARY")
    print(f"{'='*60}")
    print(f"Release: {release}")
    print(f"Title: {system_meta.get('title', 'N/A')}")
    print(f"HTML pages: {file_stats.html_files}")
    print(f"Images: {file_stats.image_files}")
    print(f"TOC entries: {toc_stats.total_entries} (orphans: {toc_stats.orphan_count})")
    print(f"Keywords: {index_stats.total_keywords}")
    print(f"Tables: {table_stats.total_tables}")
    print(f"Encodings: {dict(encoding_counter.most_common(5))}")
    print(f"Topic types (ZOOMCATEGORY): {meta_stats.zoom_categories}")
    print(f"Duplicates: {dup_stats.duplicate_groups} groups, {dup_stats.total_duplicate_pages} extra pages")

    return report


def generate_markdown_report(report: dict[str, Any], output_path: Path) -> None:
    """Generate a human-readable Markdown inventory report."""
    lines: list[str] = []

    lines.append(f"# eDocs Inventory Report — Release {report['release']}")
    lines.append("")
    lines.append(f"> Generated from: `{report['source_dir']}`")
    lines.append("")

    # System metadata
    sm = report.get("system_metadata", {})
    lines.append("## 1. CHM Metadata (#SYSTEM)")
    lines.append("")
    lines.append(f"| Field | Value |")
    lines.append(f"|---|---|")
    for k, v in sm.items():
        lines.append(f"| {k} | `{v}` |")
    lines.append("")

    # File stats
    fs = report.get("file_stats", {})
    lines.append("## 2. File Statistics")
    lines.append("")
    lines.append(f"| Metric | Count |")
    lines.append(f"|---|---|")
    lines.append(f"| Total files | {fs.get('total_files', 0)} |")
    lines.append(f"| HTML pages | {fs.get('html_files', 0)} |")
    lines.append(f"| Images | {fs.get('image_files', 0)} |")
    lines.append(f"| CSS files | {fs.get('css_files', 0)} |")
    lines.append(f"| JS files | {fs.get('js_files', 0)} |")
    lines.append(f"| Other | {fs.get('other_files', 0)} |")
    lines.append("")
    lines.append("### File Extensions")
    lines.append("")
    for ext, count in fs.get("extensions", {}).items():
        lines.append(f"- `{ext or '(no ext)'}`: {count}")
    lines.append("")

    # TOC stats
    ts = report.get("toc_stats", {})
    lines.append("## 3. Table of Contents (.hhc)")
    lines.append("")
    lines.append(f"| Metric | Count |")
    lines.append(f"|---|---|")
    lines.append(f"| Total entries | {ts.get('total_entries', 0)} |")
    lines.append(f"| Entries with page | {ts.get('entries_with_page', 0)} |")
    lines.append(f"| Entries without page (headings only) | {ts.get('entries_without_page', 0)} |")
    lines.append(f"| Max depth | {ts.get('max_depth', 0)} |")
    lines.append(f"| Orphan pages (not in TOC) | {ts.get('orphan_count', 0)} |")
    lines.append("")
    lines.append("### Depth Histogram")
    lines.append("")
    for depth, count in sorted((ts.get("depth_histogram") or {}).items(), key=lambda x: int(x[0])):
        lines.append(f"- Level {depth}: {count} entries")
    lines.append("")

    if ts.get("orphan_sample"):
        lines.append("### Sample Orphan Pages (first 20)")
        lines.append("")
        for o in ts["orphan_sample"]:
            lines.append(f"- `{o}`")
        lines.append("")

    # Index stats
    ix = report.get("index_stats", {})
    lines.append("## 4. Keyword Index (.hhk)")
    lines.append("")
    lines.append(f"| Metric | Count |")
    lines.append(f"|---|---|")
    lines.append(f"| Total keywords | {ix.get('total_keywords', 0)} |")
    lines.append(f"| Keywords with multiple targets | {ix.get('keywords_with_multiple_targets', 0)} |")
    lines.append("")

    # Meta stats
    ms = report.get("meta_stats", {})
    lines.append("## 5. HTML Meta Tags")
    lines.append("")
    lines.append("### Meta name frequency")
    lines.append("")
    lines.append(f"| Meta name | Count |")
    lines.append(f"|---|---|")
    for name, count in sorted(ms.get("meta_names", {}).items(), key=lambda x: -x[1]):
        lines.append(f"| `{name}` | {count} |")
    lines.append("")

    lines.append("### DITA Metadata Detection")
    lines.append("")
    lines.append(f"- `DC.Type` present: **{ms.get('has_dc_type', False)}**")
    lines.append(f"- `DC.Title` present: **{ms.get('has_dc_title', False)}**")
    lines.append(f"- `DC.Identifier` present: **{ms.get('has_dc_identifier', False)}**")
    lines.append(f"- `abstract` present: **{ms.get('has_abstract', False)}**")
    lines.append(f"- `keywords` present: **{ms.get('has_keywords', False)}**")
    lines.append("")

    if ms.get("zoom_categories"):
        lines.append("### ZOOMCATEGORY values (Topic Types)")
        lines.append("")
        lines.append(f"| Category | Count |")
        lines.append(f"|---|---|")
        for cat, count in sorted(ms.get("zoom_categories", {}).items(), key=lambda x: -x[1]):
            lines.append(f"| `{cat}` | {count} |")
        lines.append("")

    # Encoding stats
    lines.append("## 6. Encoding Detection")
    lines.append("")
    lines.append(f"| Encoding | Count |")
    lines.append(f"|---|---|")
    for enc, count in report.get("encoding_stats", {}).items():
        lines.append(f"| `{enc}` | {count} |")
    lines.append("")

    # CSS classes
    lines.append("## 7. Top 50 CSS Classes")
    lines.append("")
    lines.append(f"| Class | Count |")
    lines.append(f"|---|---|")
    for cls, count in sorted(report.get("css_classes_top_50", {}).items(), key=lambda x: -x[1]):
        lines.append(f"| `{cls}` | {count} |")
    lines.append("")

    # Table stats
    tb = report.get("table_stats", {})
    lines.append("## 8. Table Statistics")
    lines.append("")
    lines.append(f"Total tables: **{tb.get('total_tables', 0)}**")
    lines.append("")
    lines.append("### Column Count Histogram")
    lines.append("")
    for cols, count in sorted((tb.get("column_count_histogram") or {}).items(), key=lambda x: int(x[0])):
        lines.append(f"- {cols} columns: {count} tables")
    lines.append("")

    top_labels = tb.get("top_first_column_labels", [])
    if top_labels:
        lines.append("### Top 100 First-Column Labels")
        lines.append("")
        lines.append(f"| Label | Count |")
        lines.append(f"|---|---|")
        for item in top_labels[:100]:
            label = item.get("label", "") if isinstance(item, dict) else item[0]
            count = item.get("count", 0) if isinstance(item, dict) else item[1]
            lines.append(f"| {label} | {count} |")
        lines.append("")

    # Link stats
    ls = report.get("link_stats", {})
    lines.append("## 9. Link Statistics")
    lines.append("")
    lines.append(f"| Type | Count |")
    lines.append(f"|---|---|")
    lines.append(f"| Internal | {ls.get('internal_links', 0)} |")
    lines.append(f"| Cross-CHM | {ls.get('cross_chm_links', 0)} |")
    lines.append(f"| External | {ls.get('external_links', 0)} |")
    lines.append(f"| JavaScript | {ls.get('javascript_links', 0)} |")
    lines.append(f"| Anchor-only | {ls.get('anchor_only_links', 0)} |")
    lines.append("")

    # Content stats
    cs = report.get("content_stats", {})
    lines.append("## 10. Dynamic Content Detection")
    lines.append("")
    lines.append(f"| Feature | Pages |")
    lines.append(f"|---|---|")
    lines.append(f"| Contains `<script>` (non-standard) | {cs.get('pages_with_script', 0)} |")
    lines.append(f"| Contains `<iframe>` | {cs.get('pages_with_iframe', 0)} |")
    lines.append(f"| Contains hidden elements | {cs.get('pages_with_hidden', 0)} |")
    lines.append("")

    # Duplicate stats
    ds = report.get("duplicate_stats", {})
    lines.append("## 11. Duplicate Analysis")
    lines.append("")
    lines.append(f"| Metric | Count |")
    lines.append(f"|---|---|")
    lines.append(f"| Unique content hashes | {ds.get('total_unique_hashes', 0)} |")
    lines.append(f"| Duplicate groups | {ds.get('duplicate_groups', 0)} |")
    lines.append(f"| Total duplicate pages | {ds.get('total_duplicate_pages', 0)} |")
    lines.append("")

    if ds.get("sample_duplicates"):
        lines.append("### Sample Duplicate Groups")
        lines.append("")
        for dup in ds["sample_duplicates"]:
            lines.append(f"- **{dup['count']} copies** (hash: `{dup['hash']}`)")
            for p in dup.get("pages", []):
                lines.append(f"  - `{p}`")
        lines.append("")

    # Topic type samples
    samples = report.get("topic_type_samples", {})
    if samples:
        lines.append("## 12. Topic Type Samples")
        lines.append("")
        for ttype, paths in samples.items():
            lines.append(f"### `{ttype}`")
            lines.append("")
            for p in paths[:10]:
                lines.append(f"- `{p}`")
            lines.append("")

    output_path.write_text("\n".join(lines), encoding="utf-8")
    print(f"\nMarkdown report written to: {output_path}")


# ────────────────────────────────────────────────────────
# CLI entry point
# ────────────────────────────────────────────────────────

def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(description="eDocs CHM Inventory Tool (Phase 1)")
    parser.add_argument("extracted_dir", type=Path, help="Path to extracted CHM directory")
    parser.add_argument("--release", required=True, help="Release label (e.g. 2023.00)")
    args = parser.parse_args()

    if not args.extracted_dir.exists():
        print(f"Error: {args.extracted_dir} does not exist")
        sys.exit(1)

    # Run inventory
    report = run_inventory(args.extracted_dir, args.release)

    # Save JSON report
    json_path = Path("data/reports") / f"inventory_{args.release}.json"
    json_path.parent.mkdir(parents=True, exist_ok=True)
    json_path.write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
    print(f"\nJSON report written to: {json_path}")

    # Save Markdown report
    md_path = Path("docs") / f"inventory_{args.release}.md"
    md_path.parent.mkdir(parents=True, exist_ok=True)
    generate_markdown_report(report, md_path)


if __name__ == "__main__":
    main()
