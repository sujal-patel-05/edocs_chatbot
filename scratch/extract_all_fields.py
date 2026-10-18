import json
import sys
import time
from pathlib import Path
sys.path.insert(0, str(Path(".").resolve()))
from src.edocs.config import load_field_labels
from src.edocs.ingest.fields import extract_fields_from_doc
from src.edocs.models import FieldRecord

t0 = time.time()
extracted_dir = Path("data/extracted/edocs")
output_file = Path("data/processed/2023.00/fields.jsonl")
labels = load_field_labels()

# Load documents map to get breadcrumbs and titles
docs_file = Path("data/processed/2023.00/documents.jsonl")
doc_meta = {}
with open(docs_file, "r", encoding="utf-8") as f:
    for line in f:
        d = json.loads(line)
        doc_meta[d["path"].lower()] = {
            "title": d.get("title", ""),
            "breadcrumbs": d.get("breadcrumbs", [[]])[0] if d.get("breadcrumbs") else [],
            "doc_id": d.get("doc_id", ""),
        }

print(f"Loaded metadata for {len(doc_meta)} documents")

all_fields: list[FieldRecord] = []
html_files = [p for p in extracted_dir.rglob("*.html") if p.is_file()]
print(f"Scanning {len(html_files)} HTML files for structured fields...")

scanned = 0
for p in html_files:
    scanned += 1
    rel = str(p.relative_to(extracted_dir)).replace("\\", "/").lower()
    meta = doc_meta.get(rel, {"title": "", "breadcrumbs": [], "doc_id": f"edocs/{rel}"})

    content = p.read_text(encoding="utf-8", errors="ignore")
    # Quick filter: only process if file has tables, dl, or dta_
    if "var dta_" in content or "<table" in content or "<dl" in content:
        flds = extract_fields_from_doc(
            doc_id=meta["doc_id"],
            release="2023.00",
            html=content,
            labels=labels,
            title=meta["title"],
            breadcrumbs=meta["breadcrumbs"],
        )
        if flds:
            all_fields.extend(flds)

print(f"\nExtraction complete in {time.time() - t0:.2f}s!")
print(f"Total structured field records extracted: {len(all_fields)}")

# Breakdown by record
from collections import Counter
rec_counts = Counter(f.record for f in all_fields)
print(f"Distinct records found: {len(rec_counts)}")
print("Top records by field count:")
for r, c in rec_counts.most_common(20):
    print(f"  {r:35}: {c} fields")

# Check LOAN record specifically
loan_fields = [f for f in all_fields if f.record.upper() == "LOAN"]
print(f"\nLOAN record fields count: {len(loan_fields)}")
for f in loan_fields[:8]:
    print(f"  #{f.field_number or '---'}: {f.field_name} (Mnem: {f.poweron_mnemonic}) [{f.data_type}]")

# Write to fields.jsonl
with open(output_file, "w", encoding="utf-8") as out_f:
    for fld in all_fields:
        out_f.write(fld.model_dump_json() + "\n")

print(f"\nSuccessfully wrote {len(all_fields)} fields to {output_file}")
