from pathlib import Path
import json
import pytest
from src.edocs.models import Document, FieldRecord, DocLink

PROCESSED_DIR = Path("data/processed/2023.00")

def test_processed_documents_exist_and_validate():
    docs_file = PROCESSED_DIR / "documents.jsonl"
    assert docs_file.exists(), "documents.jsonl does not exist"

    doc_count = 0
    with open(docs_file, "r", encoding="utf-8") as f:
        for idx, line in enumerate(f):
            data = json.loads(line)
            doc = Document.model_validate(data)
            assert doc.doc_id.startswith("edocs/")
            assert doc.release == "2023.00"
            assert doc.markdown
            assert doc.content_hash
            assert len(doc.breadcrumbs) >= 1
            doc_count += 1

    assert doc_count == 7038, f"Expected 7038 documents, got {doc_count}"

def test_processed_fields_exist_and_validate():
    fields_file = PROCESSED_DIR / "fields.jsonl"
    assert fields_file.exists(), "fields.jsonl does not exist"

    field_count = 0
    with open(fields_file, "r", encoding="utf-8") as f:
        for line in f:
            data = json.loads(line)
            fld = FieldRecord.model_validate(data)
            assert fld.release == "2023.00"
            assert fld.doc_id.startswith("edocs/")
            assert fld.field_number or fld.poweron_mnemonic
            field_count += 1

    assert field_count >= 200, f"Expected at least 200 field records, got {field_count}"

def test_processed_links_exist_and_validate():
    links_file = PROCESSED_DIR / "links.jsonl"
    assert links_file.exists(), "links.jsonl does not exist"

    link_count = 0
    with open(links_file, "r", encoding="utf-8") as f:
        for idx, line in enumerate(f):
            data = json.loads(line)
            link = DocLink.model_validate(data)
            assert link.source_doc_id
            assert link.target_doc_id
            link_count += 1
            if idx >= 1000:
                break

    assert link_count >= 1000

def test_processed_reports_exist():
    reports_dir = Path("data/reports")
    summary = reports_dir / "parsing_summary_2023.00.md"
    broken_links = reports_dir / "broken_links_2023.00.json"
    failed_fields = reports_dir / "failed_fields_2023.00.json"
    samples_dir = reports_dir / "samples_parsed_2023.00"

    assert summary.exists()
    assert broken_links.exists()
    assert failed_fields.exists()
    assert samples_dir.exists()
    assert len(list(samples_dir.glob("*.md"))) == 20
