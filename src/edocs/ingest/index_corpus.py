"""
Phase 3 Chunking and Indexing Pipeline.

Reads processed documents.jsonl and fields.jsonl, produces chunks.jsonl,
tracks content hashes for incremental indexing, and stores into Postgres and Qdrant.
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
import time
from pathlib import Path
from typing import Dict, List, Set

from src.edocs.config import load_settings
from src.edocs.ingest.chunker import chunk_document, make_field_card_chunk
from src.edocs.ingest.embed import EmbeddingService
from src.edocs.models import Chunk, Document, FieldRecord, IngestStats
from src.edocs.store.pg import PostgresStore
from src.edocs.store.qdrant import QdrantVectorStore

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger("edocs.index")


def run_indexing(
    release: str = "2023.00",
    processed_dir: Path | None = None,
    force_reembed: bool = False,
) -> dict:
    start_time = time.time()
    processed_dir = (processed_dir or Path(f"data/processed/{release}")).resolve()
    docs_file = processed_dir / "documents.jsonl"
    fields_file = processed_dir / "fields.jsonl"
    chunks_file = processed_dir / "chunks.jsonl"

    if not docs_file.exists():
        raise FileNotFoundError(f"Missing {docs_file}. Run Phase 2 pipeline first.")

    settings = load_settings()

    # 1. Load documents
    logger.info("Loading documents from %s...", docs_file)
    docs_map: Dict[str, Document] = {}
    with open(docs_file, "r", encoding="utf-8") as f:
        for line in f:
            d = Document.model_validate_json(line)
            docs_map[d.doc_id] = d
    logger.info("Loaded %d documents", len(docs_map))

    # 2. Load fields
    field_records: List[FieldRecord] = []
    if fields_file.exists():
        with open(fields_file, "r", encoding="utf-8") as f:
            for line in f:
                field_records.append(FieldRecord.model_validate_json(line))
        logger.info("Loaded %d field records", len(field_records))

    keywords_list: List[dict] = []
    keywords_file = processed_dir / "keywords.jsonl"
    if keywords_file.exists():
        with open(keywords_file, "r", encoding="utf-8") as f:
            for line in f:
                keywords_list.append(json.loads(line))
        logger.info("Loaded %d keywords", len(keywords_list))

    # 3. Generate chunks
    logger.info("Generating chunks from documents and field cards...")
    all_chunks: List[Chunk] = []
    for doc in docs_map.values():
        doc_chunks = chunk_document(
            doc,
            target_tokens=settings.chunking.target_tokens,
            max_tokens=settings.chunking.max_tokens,
            table_rows_per_chunk=settings.chunking.table_rows_per_chunk,
        )
        all_chunks.extend(doc_chunks)

    # Generate field card chunks with guaranteed unique chunk_ids
    seen_chunk_ids: Set[str] = {c.chunk_id for c in all_chunks}
    for idx, fld in enumerate(field_records):
        if fld.doc_id in docs_map:
            card_chunk = make_field_card_chunk(fld, docs_map[fld.doc_id])
            if card_chunk.chunk_id in seen_chunk_ids:
                card_chunk.chunk_id = f"{card_chunk.chunk_id}_{idx}"
            seen_chunk_ids.add(card_chunk.chunk_id)
            all_chunks.append(card_chunk)

    logger.info("Generated %d total chunks", len(all_chunks))

    # Save chunks.jsonl
    with open(chunks_file, "w", encoding="utf-8") as f:
        for c in all_chunks:
            f.write(c.model_dump_json() + "\n")
    logger.info("Wrote chunks to %s", chunks_file)

    # 4. Storage & Incremental Indexing Check
    pg_store = PostgresStore(dsn=settings.postgres.dsn)
    qdrant_store = QdrantVectorStore(url=settings.qdrant.url, collection_name=settings.qdrant.collection)

    existing_hashes = pg_store.get_existing_chunk_hashes(release) if not force_reembed else {}
    logger.info("Found %d existing chunk hashes in store", len(existing_hashes))

    chunks_to_embed: List[Chunk] = []
    for c in all_chunks:
        if c.chunk_id not in existing_hashes or existing_hashes[c.chunk_id] != c.content_hash:
            chunks_to_embed.append(c)

    logger.info(
        "Incremental status: %d unchanged chunks (skipped), %d new/modified chunks to embed",
        len(all_chunks) - len(chunks_to_embed),
        len(chunks_to_embed),
    )

    # 5. Embed new/modified chunks
    embedder = EmbeddingService(
        model_name=settings.embeddings.model,
        device=settings.embeddings.device,
        batch_size=settings.embeddings.batch_size,
    )
    embedder.load_model()

    if chunks_to_embed:
        logger.info("Embedding %d chunks...", len(chunks_to_embed))
        dense_vecs, sparse_vecs = embedder.embed_chunks(chunks_to_embed)
        logger.info("Generated vectors for %d chunks", len(chunks_to_embed))

        # Upsert into Qdrant if available
        if qdrant_store.is_available:
            qdrant_store.upsert_chunks(chunks_to_embed, dense_vecs, sparse_vecs)

    # 6. Upsert metadata into Postgres/SQLite
    logger.info("Upserting documents and chunks into relational store...")
    pg_store.upsert_documents(list(docs_map.values()))
    pg_store.upsert_chunks(all_chunks)
    pg_store.upsert_fields(field_records)
    if keywords_list:
        pg_store.upsert_keywords(keywords_list)

    duration = time.time() - start_time
    stats = IngestStats(
        release=release,
        chm_hashes={"edocs.chm": "verified"},
        documents_count=len(docs_map),
        chunks_count=len(all_chunks),
        fields_count=len(field_records),
        duration_seconds=duration,
        warnings=[],
    )
    pg_store.record_ingest_run(stats)

    logger.info(
        "Phase 3 indexing complete in %.2fs. Total chunks: %d, Embedded: %d",
        duration,
        len(all_chunks),
        len(chunks_to_embed),
    )

    return {
        "release": release,
        "total_documents": len(docs_map),
        "total_chunks": len(all_chunks),
        "chunks_embedded": len(chunks_to_embed),
        "chunks_skipped": len(all_chunks) - len(chunks_to_embed),
        "duration": duration,
    }


def main():
    parser = argparse.ArgumentParser(description="Phase 3 Indexing Pipeline")
    parser.add_argument("--release", type=str, default="2023.00", help="Episys release label")
    parser.add_argument("--force-reembed", action="store_true", help="Force re-embedding all chunks")
    args = parser.parse_args()

    run_indexing(release=args.release, force_reembed=args.force_reembed)


if __name__ == "__main__":
    main()
