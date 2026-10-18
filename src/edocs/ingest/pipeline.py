"""
Phase 2 parsing pipeline for Symitar eDocs.

Reads extracted CHM directory, parses TOC, decodes and converts all HTML topics
to structured Markdown, extracts structured fields and link graph, performs deduplication,
and writes processed JSONL datasets and reports.
"""

from __future__ import annotations

import argparse
import json
import logging
import random
import sys
import time
from pathlib import Path
from typing import Dict, List, Set, Tuple
from bs4 import BeautifulSoup

from src.edocs.config import load_field_labels, load_settings
from src.edocs.ingest.chm_meta import load_system_from_dir
from src.edocs.ingest.dedupe import compute_content_hash, deduplicate_documents
from src.edocs.ingest.dita import detect_topic_type, extract_summary
from src.edocs.ingest.fields import (
    extract_field_props,
    extract_field_record,
    extract_fields_from_doc,
)
from src.edocs.ingest.html_clean import decode_html, html_to_markdown
from src.edocs.ingest.links import normalize_link
from src.edocs.ingest.sitemap import load_sitemap, walk
from src.edocs.models import DocLink, Document, FieldRecord

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger("edocs.pipeline")


def run_pipeline(
    extracted_dir: Path,
    release: str,
    output_dir: Path,
    reports_dir: Path,
    chm_name: str = "edocs",
) -> dict:
    start_time = time.time()
    extracted_dir = extracted_dir.resolve()
    output_dir = output_dir.resolve()
    reports_dir = reports_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    reports_dir.mkdir(parents=True, exist_ok=True)

    labels = load_field_labels()
    logger.info("Loaded %d field labels from config", len(labels))

    # 1. Parse #SYSTEM metadata
    sys_meta = load_system_from_dir(extracted_dir)
    chm_title = sys_meta.get("title", f"Symitar eDocs ({release})")
    hhc_rel = sys_meta.get("contents_file", "eDocs.hhc")
    hhc_path = extracted_dir / hhc_rel

    logger.info("CHM Title: %s, TOC file: %s", chm_title, hhc_rel)

    # 2. Parse TOC (.hhc)
    toc_breadcrumbs: Dict[str, List[List[str]]] = {}
    toc_order_map: Dict[str, int] = {}
    all_known_files: Set[str] = set()

    # Pre-index all files in extracted_dir (lowercase relative path)
    file_path_map: Dict[str, Path] = {}
    for p in extracted_dir.rglob("*"):
        if p.is_file():
            rel = str(p.relative_to(extracted_dir)).replace("\\", "/").lower()
            file_path_map[rel] = p
            all_known_files.add(rel)

    toc_order = 0
    toc_titles: Dict[str, str] = {}
    toc_node_count = 0

    if hhc_path.exists():
        root_node = load_sitemap(hhc_path)
        for path_tuple, node in walk(root_node):
            toc_node_count += 1
            for loc in node.locals:
                norm_loc = loc.replace("\\", "/").lower().lstrip("/")
                norm_loc, _, _ = norm_loc.partition("#")
                if norm_loc:
                    toc_order += 1
                    if norm_loc not in toc_breadcrumbs:
                        toc_breadcrumbs[norm_loc] = []
                        toc_order_map[norm_loc] = toc_order
                        toc_titles[norm_loc] = node.name
                    toc_breadcrumbs[norm_loc].append(list(path_tuple))
        logger.info(
            "Parsed TOC: %d nodes, mapped %d unique topic files",
            toc_node_count,
            len(toc_breadcrumbs),
        )
    else:
        logger.warning("TOC file %s not found", hhc_path)

    # 3. Process all HTML topics
    html_files = [p for p in extracted_dir.rglob("*") if p.suffix.lower() in (".htm", ".html")]
    logger.info("Found %d HTML files to process", len(html_files))

    raw_docs: List[Document] = []
    field_records: List[FieldRecord] = []
    all_links: List[DocLink] = []
    broken_links: List[dict] = []
    failed_fields: List[dict] = []
    keywords_list: List[dict] = []

    parsed_count = 0
    failed_parse_count = 0

    for idx, p in enumerate(html_files, 1):
        rel_path = str(p.relative_to(extracted_dir)).replace("\\", "/").lower()
        doc_id = f"{chm_name}/{rel_path}"
        current_dir = str(p.parent.relative_to(extracted_dir)).replace("\\", "/").lower()
        if current_dir == ".":
            current_dir = ""

        try:
            raw_bytes = p.read_bytes()
            decoded_text = decode_html(raw_bytes)
            soup = BeautifulSoup(decoded_text, "lxml")

            # Determine title
            title = ""
            if rel_path in toc_titles:
                title = toc_titles[rel_path]
            if not title:
                title_tag = soup.find(["title", "h1"])
                if title_tag:
                    title = title_tag.get_text().strip()
            if not title:
                title = p.stem.replace("_", " ").title()

            # Breadcrumbs & TOC order
            if rel_path in toc_breadcrumbs:
                breadcrumbs = toc_breadcrumbs[rel_path]
                toc_order_val = toc_order_map.get(rel_path)
                is_orphan = False
            else:
                folder_part = current_dir.replace("/", " > ") if current_dir else "General"
                breadcrumbs = [[chm_title, folder_part, title]]
                toc_order_val = None
                is_orphan = True

            product_area = breadcrumbs[0][0] if breadcrumbs and breadcrumbs[0] else chm_title
            topic_type = detect_topic_type(soup)
            summary = extract_summary(soup)

            # Extract keywords from meta tags
            meta_kw = soup.find("meta", attrs={"name": lambda v: v and v.lower() == "keywords"})
            if meta_kw and meta_kw.get("content"):
                for kw in meta_kw["content"].split(","):
                    kw_clean = kw.strip()
                    if kw_clean:
                        keywords_list.append({
                            "term": kw_clean,
                            "doc_id": doc_id,
                            "release": release,
                        })

            # Check links
            for a_tag in soup.find_all("a", href=True):
                href = a_tag["href"]
                link_text = a_tag.get_text().strip()
                norm = normalize_link(href, chm_name, current_dir)
                if norm is not None:
                    target_chm, target_path, anchor = norm
                    target_doc_id = f"{target_chm}/{target_path}" if target_path else doc_id
                    all_links.append(
                        DocLink(
                            source_doc_id=doc_id,
                            target_doc_id=target_doc_id,
                            anchor=anchor,
                            link_text=link_text,
                        )
                    )
                    # Check if broken (if target is within this CHM)
                    if target_chm == chm_name and target_path:
                        if target_path not in file_path_map:
                            broken_links.append({
                                "source_doc_id": doc_id,
                                "source_file": rel_path,
                                "raw_href": href,
                                "target_path": target_path,
                                "anchor": anchor,
                                "link_text": link_text,
                            })

            # Check field extraction (handles multi-field record pages and single-field pages)
            extracted_flds = extract_fields_from_doc(
                doc_id=doc_id,
                release=release,
                html=decoded_text,
                labels=labels,
                title=title,
                breadcrumbs=breadcrumbs[0] if breadcrumbs else None,
            )
            if extracted_flds:
                field_records.extend(extracted_flds)
            else:
                # Check for suspicious partial field pages
                # If page has at least 2 table cells matching known labels but failed field extraction
                raw_lower = decoded_text.lower()
                matches = [k for k in ["field number", "mnemonic", "data type", "default value", "help file"] if k in raw_lower]
                if len(matches) >= 3 and soup.find("table"):
                    failed_fields.append({
                        "doc_id": doc_id,
                        "rel_path": rel_path,
                        "title": title,
                        "matched_hints": matches,
                    })

            # Convert to Markdown and extract images
            markdown_content, images = html_to_markdown(soup, title)
            c_hash = compute_content_hash(markdown_content)

            raw_docs.append(
                Document(
                    doc_id=doc_id,
                    release=release,
                    chm=chm_name,
                    path=rel_path,
                    title=title,
                    breadcrumbs=breadcrumbs,
                    toc_order=toc_order_val,
                    topic_type=topic_type,
                    product_area=product_area,
                    summary=summary,
                    markdown=markdown_content,
                    images=images,
                    also_in=[],
                    orphan=is_orphan,
                    content_hash=c_hash,
                )
            )
            parsed_count += 1

        except Exception as e:
            failed_parse_count += 1
            logger.error("Error processing %s: %s", rel_path, e)

        if idx % 1000 == 0:
            logger.info("Processed %d / %d topics...", idx, len(html_files))

    logger.info("Completed parsing: %d success, %d failed", parsed_count, failed_parse_count)

    # 4. Deduplicate documents
    logger.info("Deduplicating %d documents...", len(raw_docs))
    deduped_docs = deduplicate_documents(raw_docs)
    logger.info("Deduplication result: %d unique documents retained", len(deduped_docs))

    # 5. Write JSONL outputs
    docs_file = output_dir / "documents.jsonl"
    with open(docs_file, "w", encoding="utf-8") as f:
        for d in deduped_docs:
            f.write(d.model_dump_json() + "\n")
    logger.info("Wrote %d documents to %s", len(deduped_docs), docs_file)

    fields_file = output_dir / "fields.jsonl"
    with open(fields_file, "w", encoding="utf-8") as f:
        for fr in field_records:
            f.write(fr.model_dump_json() + "\n")
    logger.info("Wrote %d field records to %s", len(field_records), fields_file)

    links_file = output_dir / "links.jsonl"
    with open(links_file, "w", encoding="utf-8") as f:
        for lk in all_links:
            f.write(lk.model_dump_json() + "\n")
    logger.info("Wrote %d links to %s", len(all_links), links_file)

    keywords_file = output_dir / "keywords.jsonl"
    with open(keywords_file, "w", encoding="utf-8") as f:
        for kw in keywords_list:
            f.write(json.dumps(kw) + "\n")
    logger.info("Wrote %d keywords to %s", len(keywords_list), keywords_file)

    # 6. Write reports
    broken_links_file = reports_dir / f"broken_links_{release}.json"
    with open(broken_links_file, "w", encoding="utf-8") as f:
        json.dump(broken_links, f, indent=2)

    failed_fields_file = reports_dir / f"failed_fields_{release}.json"
    with open(failed_fields_file, "w", encoding="utf-8") as f:
        json.dump(failed_fields, f, indent=2)

    # 7. Sample 20 random pages for manual review
    samples_dir = reports_dir / f"samples_parsed_{release}"
    samples_dir.mkdir(parents=True, exist_ok=True)
    random.seed(42)
    sample_docs = random.sample(deduped_docs, min(20, len(deduped_docs)))
    for s_doc in sample_docs:
        safe_name = s_doc.path.replace("/", "__").replace("\\", "__")
        sample_path = samples_dir / f"{safe_name}.md"
        with open(sample_path, "w", encoding="utf-8") as f:
            f.write(f"# {s_doc.title}\n")
            f.write(f"Doc ID: {s_doc.doc_id}\n")
            f.write(f"Type: {s_doc.topic_type}\n")
            f.write(f"Product Area: {s_doc.product_area}\n")
            f.write(f"Breadcrumbs: {' > '.join(s_doc.breadcrumbs[0])}\n")
            f.write(f"Summary: {s_doc.summary}\n")
            f.write(f"Orphan: {s_doc.orphan}\n\n")
            f.write("---\n\n")
            f.write(s_doc.markdown)

    duration = time.time() - start_time

    # 8. Markdown summary report
    summary_md = f"""# Phase 2 Parsing Summary — Release {release}

- **Date**: {time.strftime('%Y-%m-%d %H:%M:%S')}
- **Duration**: {duration:.2f} seconds
- **Source Extracted Directory**: `{extracted_dir}`

## Metrics

| Metric | Value |
|---|---|
| Total HTML Files Found | {len(html_files)} |
| Successfully Parsed Topics | {parsed_count} ({parsed_count / len(html_files) * 100:.2f}%) |
| Failed Parsing | {failed_parse_count} |
| Unique Documents (after dedupe) | {len(deduped_docs)} |
| Extracted Field Records | {len(field_records)} |
| Total Links Extracted | {len(all_links)} |
| Broken Internal Links Found | {len(broken_links)} |
| Suspicious Unextracted Field Pages | {len(failed_fields)} |
| Keywords Extracted | {len(keywords_list)} |
| Manual Review Samples Generated | {len(sample_docs)} |

## Output Artifacts

- **Documents**: `data/processed/{release}/documents.jsonl`
- **Fields**: `data/processed/{release}/fields.jsonl`
- **Links**: `data/processed/{release}/links.jsonl`
- **Keywords**: `data/processed/{release}/keywords.jsonl`
- **Broken Links Report**: `data/reports/broken_links_{release}.json`
- **Failed Fields Report**: `data/reports/failed_fields_{release}.json`
- **Review Samples**: `data/reports/samples_parsed_{release}/`
"""
    summary_path = reports_dir / f"parsing_summary_{release}.md"
    with open(summary_path, "w", encoding="utf-8") as f:
        f.write(summary_md)

    logger.info("Summary report written to %s", summary_path)

    return {
        "total_html": len(html_files),
        "parsed_count": parsed_count,
        "failed_parse_count": failed_parse_count,
        "deduped_docs": len(deduped_docs),
        "field_records": len(field_records),
        "broken_links": len(broken_links),
        "failed_fields": len(failed_fields),
        "duration": duration,
    }


def main():
    parser = argparse.ArgumentParser(description="Phase 2 Ingestion Pipeline")
    parser.add_argument("extracted_dir", type=str, help="Path to extracted CHM directory")
    parser.add_argument("--release", type=str, default="2023.00", help="Episys release label")
    parser.add_argument("--output-dir", type=str, default="data/processed/2023.00", help="Output directory")
    parser.add_argument("--reports-dir", type=str, default="data/reports", help="Reports directory")
    parser.add_argument("--chm-name", type=str, default="edocs", help="CHM name stem")

    args = parser.parse_args()
    run_pipeline(
        extracted_dir=Path(args.extracted_dir),
        release=args.release,
        output_dir=Path(args.output_dir),
        reports_dir=Path(args.reports_dir),
        chm_name=args.chm_name,
    )


if __name__ == "__main__":
    main()
