"""
DITA topic and table-aware chunking module.

Rules:
1. Topic page is primary unit. If topic <= max_tokens, emit one chunk.
2. Long topics split at headings, then at paragraph boundaries.
3. Never split inside a table, code block, numbered procedure, or note.
4. Tables longer than table_rows_per_chunk split by row groups with header repeated (kind="table_part").
5. Procedures longer than max_tokens split between top-level steps (kind="steps_part").
6. Standard chunk header prepended to all chunks.
7. Generates compact field cards for field reference pages (kind="field_card").
"""

from __future__ import annotations

import hashlib
import re
from typing import List, Optional
import tiktoken
from src.edocs.models import Document, Chunk, FieldRecord

_enc = tiktoken.get_encoding("cl100k_base")


def count_tokens(text: str) -> int:
    """Count tokens in text using cl100k_base."""
    return len(_enc.encode(text))


def build_chunk_header(doc: Document, section_title: Optional[str] = None) -> str:
    """Build standardized chunk header."""
    bc_str = " > ".join(doc.breadcrumbs[0]) if doc.breadcrumbs else doc.title
    title_str = f"{doc.title} > {section_title}" if section_title else doc.title
    summary_str = doc.summary or "N/A"
    return (
        f"[Release {doc.release}] {doc.product_area} > {bc_str} > {title_str}\n"
        f"Type: {doc.topic_type}. Summary: {summary_str}\n\n"
    )


def _split_long_table(
    table_md: str,
    doc: Document,
    section_name: str,
    base_chunk_idx: int,
    rows_per_chunk: int = 25,
) -> List[Chunk]:
    """Split a long markdown table into row groups, repeating the header row."""
    lines = [line.strip() for line in table_md.strip().splitlines() if line.strip()]
    if len(lines) < 3:
        return []

    header_line = lines[0]
    sep_line = lines[1]
    data_rows = lines[2:]

    chunks: List[Chunk] = []
    chunk_idx = base_chunk_idx

    for i in range(0, len(data_rows), rows_per_chunk):
        group_rows = data_rows[i : i + rows_per_chunk]
        part_md = "\n".join([header_line, sep_line] + group_rows)
        header = build_chunk_header(
            doc, f"{section_name} (Table rows {i + 1}–{i + len(group_rows)})"
        )
        full_text = header + part_md
        chunk_id = f"{doc.doc_id}#tbl_{chunk_idx}"
        chunks.append(
            Chunk(
                chunk_id=chunk_id,
                doc_id=doc.doc_id,
                release=doc.release,
                text=full_text,
                section_path=[doc.title, section_name],
                anchor=None,
                topic_type=doc.topic_type,
                product_area=doc.product_area,
                kind="table_part",
                token_count=count_tokens(full_text),
                content_hash=hashlib.sha256(full_text.encode("utf-8")).hexdigest(),
            )
        )
        chunk_idx += 1

    return chunks


def _split_long_procedure(
    proc_md: str,
    doc: Document,
    section_name: str,
    base_chunk_idx: int,
    max_tokens: int = 800,
) -> List[Chunk]:
    """Split a long numbered procedure between top-level steps."""
    step_items = re.split(r"(?=(?:\n|^)\d+\.\s+)", proc_md)
    step_items = [s.strip() for s in step_items if s.strip()]

    chunks: List[Chunk] = []
    chunk_idx = base_chunk_idx
    cur_steps: List[str] = []
    cur_tokens = 0
    start_step = 1

    header_prefix = build_chunk_header(doc, section_name)
    header_tokens = count_tokens(header_prefix)

    for idx, step in enumerate(step_items, 1):
        s_tokens = count_tokens(step)
        if cur_tokens + s_tokens > (max_tokens - header_tokens) and cur_steps:
            end_step = start_step + len(cur_steps) - 1
            body = "\n\n".join(cur_steps)
            header = build_chunk_header(
                doc, f"{section_name} (Steps {start_step}–{end_step})"
            )
            full_text = header + body
            chunks.append(
                Chunk(
                    chunk_id=f"{doc.doc_id}#steps_{chunk_idx}",
                    doc_id=doc.doc_id,
                    release=doc.release,
                    text=full_text,
                    section_path=[doc.title, section_name],
                    anchor=None,
                    topic_type="task",
                    product_area=doc.product_area,
                    kind="steps_part",
                    token_count=count_tokens(full_text),
                    content_hash=hashlib.sha256(full_text.encode("utf-8")).hexdigest(),
                )
            )
            chunk_idx += 1
            cur_steps = [step]
            cur_tokens = s_tokens
            start_step = idx
        else:
            cur_steps.append(step)
            cur_tokens += s_tokens

    if cur_steps:
        end_step = start_step + len(cur_steps) - 1
        body = "\n\n".join(cur_steps)
        header = build_chunk_header(
            doc, f"{section_name} (Steps {start_step}–{end_step})"
        )
        full_text = header + body
        chunks.append(
            Chunk(
                chunk_id=f"{doc.doc_id}#steps_{chunk_idx}",
                doc_id=doc.doc_id,
                release=doc.release,
                text=full_text,
                section_path=[doc.title, section_name],
                anchor=None,
                topic_type="task",
                product_area=doc.product_area,
                kind="steps_part",
                token_count=count_tokens(full_text),
                content_hash=hashlib.sha256(full_text.encode("utf-8")).hexdigest(),
            )
        )

    return chunks


def chunk_document(
    doc: Document,
    target_tokens: int = 450,
    max_tokens: int = 800,
    table_rows_per_chunk: int = 25,
) -> List[Chunk]:
    """
    Chunk a Document into one or more Chunk objects.
    """
    total_tokens = count_tokens(doc.markdown)
    header = build_chunk_header(doc)
    header_tokens = count_tokens(header)

    # 1. If document fits within max_tokens, emit single topic chunk
    if total_tokens + header_tokens <= max_tokens:
        full_text = header + doc.markdown
        chunk_id = f"{doc.doc_id}#0"
        return [
            Chunk(
                chunk_id=chunk_id,
                doc_id=doc.doc_id,
                release=doc.release,
                text=full_text,
                section_path=[doc.title],
                anchor=None,
                topic_type=doc.topic_type,
                product_area=doc.product_area,
                kind="topic",
                token_count=count_tokens(full_text),
                content_hash=hashlib.sha256(full_text.encode("utf-8")).hexdigest(),
            )
        ]

    # 2. Check if the entire topic is a huge table
    table_match = re.search(r"((?:\|[^\n]+\|\n)+)", doc.markdown)
    if table_match and count_tokens(table_match.group(1)) > (max_tokens - header_tokens):
        lines = [l for l in table_match.group(1).splitlines() if l.strip().startswith("|")]
        if len(lines) > table_rows_per_chunk:
            return _split_long_table(
                table_match.group(1), doc, doc.title, 0, table_rows_per_chunk
            )

    # 3. Check if the topic is a huge ordered procedure
    if doc.topic_type == "task" and re.search(r"(?:\n|^)1\.\s+", doc.markdown):
        step_items = re.findall(r"(?:\n|^)\d+\.\s+", doc.markdown)
        if len(step_items) > 10 and total_tokens > (max_tokens - header_tokens):
            return _split_long_procedure(doc.markdown, doc, doc.title, 0, max_tokens)

    # 4. Standard heading / section split
    chunks: List[Chunk] = []
    sections = re.split(r"(?=(?:\n|^)#{1,4}\s+)", doc.markdown)

    chunk_idx = 0
    cur_text_parts: List[str] = []
    cur_section_name = doc.title
    cur_tokens = 0

    for sec in sections:
        sec = sec.strip()
        if not sec:
            continue

        sec_header_match = re.match(r"^#{1,4}\s+(.+)$", sec, re.M)
        if sec_header_match:
            cur_section_name = sec_header_match.group(1).strip()

        sec_tokens = count_tokens(sec)

        # Check if this single section is a table that needs splitting
        if sec_tokens > (max_tokens - header_tokens) and sec.startswith("|"):
            if cur_text_parts:
                body = "\n\n".join(cur_text_parts)
                full_text = build_chunk_header(doc, cur_section_name) + body
                chunks.append(
                    Chunk(
                        chunk_id=f"{doc.doc_id}#{chunk_idx}",
                        doc_id=doc.doc_id,
                        release=doc.release,
                        text=full_text,
                        section_path=[doc.title, cur_section_name],
                        anchor=None,
                        topic_type=doc.topic_type,
                        product_area=doc.product_area,
                        kind="topic",
                        token_count=count_tokens(full_text),
                        content_hash=hashlib.sha256(full_text.encode("utf-8")).hexdigest(),
                    )
                )
                chunk_idx += 1
                cur_text_parts = []
                cur_tokens = 0

            tbl_chunks = _split_long_table(
                sec, doc, cur_section_name, chunk_idx, table_rows_per_chunk
            )
            chunks.extend(tbl_chunks)
            chunk_idx += len(tbl_chunks)
            continue

        if cur_tokens + sec_tokens > (max_tokens - header_tokens) and cur_text_parts:
            body = "\n\n".join(cur_text_parts)
            full_text = build_chunk_header(doc, cur_section_name) + body
            chunks.append(
                Chunk(
                    chunk_id=f"{doc.doc_id}#{chunk_idx}",
                    doc_id=doc.doc_id,
                    release=doc.release,
                    text=full_text,
                    section_path=[doc.title, cur_section_name],
                    anchor=None,
                    topic_type=doc.topic_type,
                    product_area=doc.product_area,
                    kind="topic",
                    token_count=count_tokens(full_text),
                    content_hash=hashlib.sha256(full_text.encode("utf-8")).hexdigest(),
                )
            )
            chunk_idx += 1
            cur_text_parts = [sec]
            cur_tokens = sec_tokens
        else:
            cur_text_parts.append(sec)
            cur_tokens += sec_tokens

    if cur_text_parts:
        body = "\n\n".join(cur_text_parts)
        full_text = build_chunk_header(doc, cur_section_name) + body
        chunks.append(
            Chunk(
                chunk_id=f"{doc.doc_id}#{chunk_idx}",
                doc_id=doc.doc_id,
                release=doc.release,
                text=full_text,
                section_path=[doc.title, cur_section_name],
                anchor=None,
                topic_type=doc.topic_type,
                product_area=doc.product_area,
                kind="topic",
                token_count=count_tokens(full_text),
                content_hash=hashlib.sha256(full_text.encode("utf-8")).hexdigest(),
            )
        )

    return chunks


def make_field_card_chunk(field: FieldRecord, doc: Document) -> Chunk:
    """Generate a compact field card chunk for a FieldRecord."""
    header = build_chunk_header(doc, f"Field: {field.field_name}")
    card_parts = [
        f"Record: {field.record}",
        f"Field: {field.field_name}",
    ]
    if field.field_number:
        card_parts.append(f"Field Number: {field.field_number}")
    if field.poweron_mnemonic:
        card_parts.append(f"PowerOn Mnemonic: {field.poweron_mnemonic}")
    if field.symxchange_mnemonic:
        card_parts.append(f"SymXchange Mnemonic: {field.symxchange_mnemonic}")
    if field.data_type:
        card_parts.append(f"Data Type: {field.data_type}")
    if field.source:
        card_parts.append(f"Source: {field.source}")
    if field.help_file:
        card_parts.append(f"Help File: {field.help_file}")
    if field.default_control:
        card_parts.append(f"Default Control: {field.default_control}")
    if field.default_value:
        card_parts.append(f"Default Value: {field.default_value}")
    if field.description:
        card_parts.append(f"Description: {field.description}")

    card_text = " | ".join(card_parts)
    full_text = header + card_text
    fld_key = None
    if field.poweron_mnemonic and field.poweron_mnemonic.strip().upper() not in ("NONE", "N/A", "NULL"):
        fld_key = field.poweron_mnemonic.strip()
    elif field.field_number and field.field_number.strip().upper() not in ("NONE", "N/A", "NULL"):
        fld_key = field.field_number.strip()
    else:
        clean_name = re.sub(r'[^a-zA-Z0-9_]', '', field.field_name)
        fld_key = clean_name or "0"
    chunk_id = f"{doc.doc_id}#field_{fld_key}"

    return Chunk(
        chunk_id=chunk_id,
        doc_id=doc.doc_id,
        release=doc.release,
        text=full_text,
        section_path=[doc.title, field.record, field.field_name],
        anchor=None,
        topic_type="reference",
        product_area=doc.product_area,
        kind="field_card",
        token_count=count_tokens(full_text),
        content_hash=hashlib.sha256(full_text.encode("utf-8")).hexdigest(),
    )
