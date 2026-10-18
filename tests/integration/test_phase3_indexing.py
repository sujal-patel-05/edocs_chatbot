from pathlib import Path
import json
import pytest
from src.edocs.models import Chunk
from src.edocs.store.pg import PostgresStore
from src.edocs.ingest.index_corpus import run_indexing

CHUNKS_FILE = Path("data/processed/2023.00/chunks.jsonl")

def test_chunks_file_exists_and_validates():
    assert CHUNKS_FILE.exists(), "chunks.jsonl does not exist"

    kinds_found = set()
    total_chunks = 0
    with open(CHUNKS_FILE, "r", encoding="utf-8") as f:
        for line in f:
            c = Chunk.model_validate_json(line)
            assert c.chunk_id
            assert c.release == "2023.00"
            assert "[Release 2023.00]" in c.text
            assert c.content_hash
            assert c.token_count > 0
            kinds_found.add(c.kind)
            total_chunks += 1

    assert total_chunks >= 15000
    assert "topic" in kinds_found
    assert "field_card" in kinds_found

def test_incremental_reindex_embeds_zero():
    # Running index_corpus without modifications should embed exactly 0 chunks
    res = run_indexing(release="2023.00", force_reembed=False)
    assert res["total_chunks"] >= 15000
    assert res["chunks_embedded"] == 0

def test_store_field_search():
    store = PostgresStore("postgresql://localhost:5432/edocs")
    # Search for known fields in the database
    results = store.search_fields(query="COMMENT", release="2023.00")
    assert len(results) >= 1
    assert any("COMMENT" in (r.poweron_mnemonic or "") for r in results)
