import subprocess
import os
import sys
from pathlib import Path
from collections import Counter

CHM_PATH = Path(r"c:\Users\Sujal Patel\Desktop\eDocs_Chatbot\eDocs.chm")
EXTRACTED_DIR = Path(r"c:\Users\Sujal Patel\Desktop\eDocs_Chatbot\data\extracted\edocs")
SEVEN_ZIP = Path(r"C:\Program Files\7-Zip\7z.exe")

print("Checking 7-Zip listing...")
cmd = [str(SEVEN_ZIP), "l", "-slt", str(CHM_PATH)]
proc = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")

chm_files = {}
current = {}
for line in proc.stdout.splitlines():
    line = line.strip()
    if not line:
        if "Path" in current:
            # Check if directory
            is_dir = "D" in current.get("Attributes", "") or current.get("Folder") == "+"
            if not is_dir:
                p = current["Path"].replace("\\", "/")
                chm_files[p.lower()] = {
                    "raw_path": current["Path"],
                    "size": int(current.get("Size", 0)),
                }
        current = {}
    elif "=" in line:
        k, v = line.split("=", 1)
        current[k.strip()] = v.strip()

if "Path" in current:
    is_dir = "D" in current.get("Attributes", "") or current.get("Folder") == "+"
    if not is_dir:
        p = current["Path"].replace("\\", "/")
        chm_files[p.lower()] = {
            "raw_path": current["Path"],
            "size": int(current.get("Size", 0)),
        }

print(f"Total files in CHM: {len(chm_files)}")

# Check extracted files on disk
extracted_files = {}
for p in EXTRACTED_DIR.rglob("*"):
    if p.is_file():
        rel = str(p.relative_to(EXTRACTED_DIR)).replace("\\", "/").lower()
        extracted_files[rel] = {
            "path": p,
            "size": p.stat().st_size,
        }

print(f"Total files in extracted dir: {len(extracted_files)}")

# Compare
missing_in_extracted = set(chm_files.keys()) - set(extracted_files.keys())
extra_in_extracted = set(extracted_files.keys()) - set(chm_files.keys())

print(f"Missing in extracted: {len(missing_in_extracted)}")
print(f"Extra in extracted: {len(extra_in_extracted)}")

if missing_in_extracted:
    print("Sample missing files:")
    for m in list(missing_in_extracted)[:20]:
        print("  -", m, chm_files[m]["size"], "bytes")

# Extension breakdown
from collections import Counter
ext_counter = Counter(Path(k).suffix.lower() for k in extracted_files.keys())
print("\nFile types in extracted directory:")
for ext, count in ext_counter.most_common():
    label = ext if ext else "[no extension]"
    print(f"  {label:15}: {count}")

# Check documents.jsonl
DOCS_PATH = Path(r"c:\Users\Sujal Patel\Desktop\eDocs_Chatbot\data\processed\2023.00\documents.jsonl")
import json

if DOCS_PATH.exists():
    doc_paths = set()
    empty_docs = []
    total_docs = 0
    with open(DOCS_PATH, "r", encoding="utf-8") as f:
        for line in f:
            total_docs += 1
            data = json.loads(line)
            doc_paths.add(data["path"].lower())
            if not data.get("markdown") or len(data["markdown"].strip()) == 0:
                empty_docs.append(data["path"])

    print(f"\nProcessed documents.jsonl:")
    print(f"  Total records: {total_docs}")
    print(f"  Unique paths: {len(doc_paths)}")
    print(f"  Empty content docs: {len(empty_docs)}")
    
    ext_html = {k: v for k, v in extracted_files.items() if k.endswith((".html", ".htm"))}
    missing_docs = set(ext_html.keys()) - doc_paths
    print(f"  HTML files not in documents.jsonl: {len(missing_docs)}")
    if missing_docs:
        print("  Sample missing:", list(missing_docs)[:10])

# Check chunks.jsonl
CHUNKS_PATH = Path(r"c:\Users\Sujal Patel\Desktop\eDocs_Chatbot\data\processed\2023.00\chunks.jsonl")
if CHUNKS_PATH.exists():
    total_chunks = 0
    chunk_docs = set()
    with open(CHUNKS_PATH, "r", encoding="utf-8") as f:
        for line in f:
            total_chunks += 1
            data = json.loads(line)
            chunk_docs.add(data["doc_id"])
    print(f"\nChunks dataset:")
    print(f"  Total chunks: {total_chunks}")
    print(f"  Distinct doc_ids chunked: {len(chunk_docs)}")

# Check fields.jsonl
FIELDS_PATH = Path(r"c:\Users\Sujal Patel\Desktop\eDocs_Chatbot\data\processed\2023.00\fields.jsonl")
if FIELDS_PATH.exists():
    with open(FIELDS_PATH, "r", encoding="utf-8") as f:
        field_count = sum(1 for _ in f)
    print(f"\nFields dataset:")
    print(f"  Total field records: {field_count}")

# Check SQLite DB
DB_PATH = Path(r"c:\Users\Sujal Patel\Desktop\eDocs_Chatbot\data\edocs.db")
if DB_PATH.exists():
    import sqlite3
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
    tables = [row[0] for row in cursor.fetchall()]
    print(f"\nDatabase tables in edocs.db: {tables}")
    for table in tables:
        if not table.startswith("sqlite_"):
            try:
                cursor.execute(f"SELECT COUNT(*) FROM [{table}]")
                cnt = cursor.fetchone()[0]
                print(f"  Table {table}: {cnt} rows")
            except Exception as e:
                print(f"  Table {table}: error {e}")
    conn.close()

