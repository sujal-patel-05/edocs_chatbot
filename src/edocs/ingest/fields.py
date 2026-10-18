"""
Field and record extraction module for Symitar reference pages.

Extracts structured field properties (Field Number, Mnemonic, Data Type,
Help File, Default Control, Default Value, Source, etc.) from tables and definition lists.
"""

from __future__ import annotations

import re
from typing import Optional
from bs4 import BeautifulSoup
from src.edocs.models import FieldRecord


def _norm(s: str) -> str:
    """Normalize label string: collapse whitespace, trim, strip colon, lowercase."""
    return re.sub(r"\s+", " ", s).strip().rstrip(":").lower()


def extract_field_props(html: str, labels: dict[str, str]) -> dict[str, str] | None:
    """
    Extract field properties from HTML using the label mapping from field_labels.yaml.

    Returns dictionary of property_name -> value if at least field_number or
    poweron_mnemonic is found, else None.
    """
    soup = BeautifulSoup(html, "lxml")
    found: dict[str, str] = {}

    # Extract from 2-column tables
    for tr in soup.find_all("tr"):
        cells = tr.find_all(["th", "td"])
        if len(cells) == 2:
            label_text = _norm(cells[0].get_text(" "))
            if label_text in labels:
                col = labels[label_text]
                val = re.sub(r"\s+", " ", cells[1].get_text(" ")).strip()
                if val:
                    found[col] = val

    # Extract from dl/dt/dd pairs
    for dt in soup.find_all("dt"):
        dd = dt.find_next_sibling("dd")
        if dd:
            label_text = _norm(dt.get_text(" "))
            if label_text in labels:
                col = labels[label_text]
                val = re.sub(r"\s+", " ", dd.get_text(" ")).strip()
                if val:
                    found.setdefault(col, val)

    # Validate that this is indeed a field reference page
    if "field_number" in found or "poweron_mnemonic" in found:
        return found
    return None


def extract_field_record(
    doc_id: str,
    release: str,
    html: str,
    labels: dict[str, str],
    title: str = "",
    breadcrumbs: list[str] | None = None,
) -> Optional[FieldRecord]:
    """
    Extract a structured FieldRecord model from a topic page.
    """
    props = extract_field_props(html, labels)
    if not props:
        return None

    # Derive record name from breadcrumbs or title if available
    record_name = props.get("record_name", "")
    if not record_name and breadcrumbs:
        # Usually in Symitar eDocs breadcrumb: ... > Account Records > Field Name
        for b in reversed(breadcrumbs):
            if "record" in b.lower() or "file" in b.lower():
                record_name = b.replace(" Records", "").replace(" File", "").strip()
                break
        if not record_name and len(breadcrumbs) >= 2:
            record_name = breadcrumbs[-2]

    field_name = props.get("field_name", title or "Unknown")

    # Extract first paragraph as description if not already in props
    desc = props.get("description")
    if not desc:
        soup = BeautifulSoup(html, "lxml")
        p = soup.find("p")
        if p:
            desc = re.sub(r"\s+", " ", p.get_text(" ")).strip()

    return FieldRecord(
        release=release,
        record=record_name or "General",
        field_name=field_name,
        field_number=props.get("field_number"),
        poweron_mnemonic=props.get("poweron_mnemonic"),
        symxchange_mnemonic=props.get("symxchange_mnemonic"),
        data_type=props.get("data_type"),
        source=props.get("source"),
        help_file=props.get("help_file"),
        default_control=props.get("default_control"),
        default_value=props.get("default_value"),
        description=desc,
        doc_id=doc_id,
    )


def extract_fields_from_doc(
    doc_id: str,
    release: str,
    html: str,
    labels: dict[str, str],
    title: str = "",
    breadcrumbs: list[str] | None = None,
) -> list[FieldRecord]:
    """
    Extract all structured FieldRecord models from a topic page.
    Handles both multi-field record definition pages (with dynamic dta_ arrays)
    and single-field / key-value pages.
    """
    results: list[FieldRecord] = []

    # 1. Multi-field record pages (Symitar Table of Fields)
    if "var dta_" in html:
        # Extract PowerOn record name
        m_pon = re.search(
            r"PowerOn record name[^<]*:[^<]*<ul[^>]*>\s*<li[^>]*>([^<]+)</li>",
            html,
            re.IGNORECASE,
        )
        if m_pon:
            record_name = m_pon.group(1).strip()
        else:
            clean_title = (
                title.replace("Record Fields", "")
                .replace("Record Field", "")
                .replace("Fields", "")
                .replace("Record", "")
                .strip()
            )
            record_name = clean_title.upper() if clean_title else "GENERAL"

        pattern = re.compile(
            r"\[\s*'([^']*)'\s*,\s*'(\d+)'\s*,\s*'([^']*)'\s*,\s*'([^']*)'\s*,\s*'([^']*)'\s*,\s*'([^']*)'\s*,\s*'([^']*)'"
        )
        matches = pattern.findall(html)

        for sec_id, order, fld_name, fld_num, mnem, dtype, help_no in matches:
            if not fld_name or fld_name == "&nbsp;":
                continue

            desc = ""
            source = None
            default_val = None
            default_ctrl = None
            sym_mnem = None
            code_options: list[str] = []

            pos = html.find(f'id="{sec_id}"')
            if pos != -1:
                next_pos = html.find('class="section"', pos + 25)
                sec_chunk = html[pos:next_pos] if next_pos != -1 else html[pos : pos + 6000]

                # Extract first paragraph description
                p_m = re.search(r"<p[^>]*>(.*?)</p>", sec_chunk, re.DOTALL)
                if p_m:
                    desc_text = re.sub(r"<[^>]+>", " ", p_m.group(1))
                    desc = re.sub(r"\s+", " ", desc_text).strip()

                # Extract table key-values
                for tr_m in re.finditer(
                    r"<tr[^>]*>\s*<td[^>]*>(.*?)</td>\s*<td[^>]*>(.*?)</td>\s*</tr>",
                    sec_chunk,
                    re.DOTALL,
                ):
                    lbl = re.sub(r"<[^>]+>", " ", tr_m.group(1)).strip().lower()
                    val = re.sub(r"<[^>]+>", " ", tr_m.group(2)).strip()
                    if "source" in lbl:
                        source = val
                    elif "default value" in lbl:
                        default_val = val
                    elif "default control" in lbl:
                        default_ctrl = val
                    elif "symxchange" in lbl:
                        sym_mnem = val

                # Extract code values / options (e.g. (0) Closed End, (1) Open End)
                for opt_m in re.finditer(
                    r"<dt[^>]*>.*?<span class=\"option\">(.*?)</span>.*?</dt>\s*<dd[^>]*>(.*?)</dd>",
                    sec_chunk,
                    re.DOTALL,
                ):
                    opt_title = re.sub(r"<[^>]+>", " ", opt_m.group(1)).strip()
                    opt_desc = re.sub(r"<[^>]+>", " ", opt_m.group(2)).strip()
                    opt_desc_short = opt_desc.split(".")[0] if "." in opt_desc else opt_desc[:80]
                    code_options.append(f"{opt_title}: {opt_desc_short}")

            if code_options:
                codes_summary = " Codes: " + "; ".join(code_options[:10])
                desc = (desc + codes_summary).strip() if desc else codes_summary.strip()

            clean_mnem = None if mnem in ("N/A", "None", "") else mnem.strip()
            clean_num = None if fld_num in ("N/A", "None", "") else fld_num.strip()
            clean_help = None if help_no in ("N/A", "None", "") else help_no.strip()

            if not clean_mnem and not clean_num:
                continue

            results.append(
                FieldRecord(
                    release=release,
                    record=record_name,
                    field_name=fld_name.strip(),
                    field_number=clean_num,
                    poweron_mnemonic=clean_mnem,
                    symxchange_mnemonic=sym_mnem,
                    data_type=dtype.strip() if dtype else None,
                    source=source,
                    help_file=clean_help,
                    default_control=default_ctrl,
                    default_value=default_val,
                    description=desc or fld_name.strip(),
                    doc_id=doc_id,
                )
            )

    # 2. Fallback to single-field extraction if no multi-field table found
    if not results:
        single_rec = extract_field_record(
            doc_id=doc_id,
            release=release,
            html=html,
            labels=labels,
            title=title,
            breadcrumbs=breadcrumbs,
        )
        if single_rec:
            results.append(single_rec)

    return results

