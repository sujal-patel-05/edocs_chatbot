import hashlib
import json
import sys
import time
from pathlib import Path
from collections import defaultdict

sys.path.insert(0, str(Path(".").resolve()))
from src.edocs.models import Document, Chunk, FieldRecord
from src.edocs.ingest.chunker import chunk_document, make_field_card_chunk, count_tokens
from src.edocs.store.pg import PostgresStore

t0 = time.time()
docs_file = Path("data/processed/2023.00/documents.jsonl")
fields_file = Path("data/processed/2023.00/fields.jsonl")
chunks_file = Path("data/processed/2023.00/chunks.jsonl")
db_path = Path("data/edocs.db")

# 1. Load documents
print("Loading documents...")
docs_map = {}
with open(docs_file, "r", encoding="utf-8") as f:
    for line in f:
        d = Document.model_validate_json(line)
        docs_map[d.doc_id] = d
print(f"Loaded {len(docs_map)} documents")

# 2. Load fields
print("Loading fields...")
fields = []
fields_by_doc = defaultdict(list)
fields_by_rec = defaultdict(list)

with open(fields_file, "r", encoding="utf-8") as f:
    for line in f:
        fr = FieldRecord.model_validate_json(line)
        fields.append(fr)
        fields_by_doc[fr.doc_id].append(fr)
        fields_by_rec[fr.record.upper()].append(fr)

print(f"Loaded {len(fields)} fields across {len(fields_by_rec)} records")

# 3. Generate chunks
print("Generating document topic chunks...")
all_chunks: list[Chunk] = []
for doc in docs_map.values():
    doc_chunks = chunk_document(doc)
    all_chunks.extend(doc_chunks)

print(f"Generated {len(all_chunks)} base document chunks")

# 4. Generate field card chunks
print("Generating field card chunks...")
seen_chunk_ids = {c.chunk_id for c in all_chunks}
field_cards_count = 0

for fr in fields:
    if fr.doc_id in docs_map:
        doc = docs_map[fr.doc_id]
        card = make_field_card_chunk(fr, doc)
        if card.chunk_id not in seen_chunk_ids:
            all_chunks.append(card)
            seen_chunk_ids.add(card.chunk_id)
            field_cards_count += 1

print(f"Generated {field_cards_count} field card chunks")

# 5. Generate Record Overview chunks for major records
print("Generating record overview chunks...")
record_overview_count = 0
for rec_name, rec_fields in fields_by_rec.items():
    if not rec_fields:
        continue
    first_fld = rec_fields[0]
    if first_fld.doc_id not in docs_map:
        continue
    doc = docs_map[first_fld.doc_id]

    # Build a comprehensive structured overview table of fields
    lines = [
        f"[Release 2023.00] {doc.product_area} > {doc.title} > {rec_name} Record Overview",
        f"Type: reference. Summary: Overview of the {rec_name} record and its complete field definitions.",
        "",
        f"# {doc.title} ({rec_name})",
        "",
        f"PowerOn Record Name: **{rec_name}**",
        "",
        f"{doc.summary or 'This document contains field definitions and descriptions for the ' + rec_name + ' record.'}",
        "",
        "## Table of Fields",
        "",
        "| Field # | Field Name | Mnemonic | Data Type | Description |",
        "|---|---|---|---|---|",
    ]

    for f in rec_fields[:50]:  # Top 50 core fields in record overview
        f_num = f.field_number or "—"
        f_name = f.field_name
        f_mnem = f.poweron_mnemonic or "—"
        f_type = f.data_type or "—"
        f_desc = (f.description or "").split(".")[0].replace("|", "\\|")
        lines.append(f"| {f_num} | {f_name} | {f_mnem} | {f_type} | {f_desc} |")

    overview_text = "\n".join(lines)
    overview_chunk_id = f"{doc.doc_id}#record_overview"
    if overview_chunk_id not in seen_chunk_ids:
        all_chunks.append(
            Chunk(
                chunk_id=overview_chunk_id,
                doc_id=doc.doc_id,
                release=doc.release,
                text=overview_text,
                section_path=[doc.title, rec_name, "Record Overview"],
                anchor=None,
                topic_type="reference",
                product_area=doc.product_area,
                kind="record_overview",
                token_count=count_tokens(overview_text),
                content_hash=hashlib.sha256(overview_text.encode("utf-8")).hexdigest(),
            )
        )
        seen_chunk_ids.add(overview_chunk_id)
        record_overview_count += 1

print(f"Generated {record_overview_count} record overview chunks")
print(f"Total chunks to write: {len(all_chunks)}")

# 6. Write chunks.jsonl
print("Writing chunks.jsonl...")
with open(chunks_file, "w", encoding="utf-8") as out_f:
    for c in all_chunks:
        out_f.write(c.model_dump_json() + "\n")

# 7. Update SQLite DB
print("Updating edocs.db SQLite database...")
store = PostgresStore(dsn="", sqlite_fallback_path=db_path)
store.upsert_fields(fields)
store.upsert_chunks(all_chunks)

print(f"\nAll operations completed in {time.time() - t0:.2f}s!")
