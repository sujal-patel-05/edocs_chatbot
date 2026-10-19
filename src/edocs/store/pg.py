"""
PostgreSQL storage backend with SQLite fallback for local development.

Manages documents, chunks, structured fields, keywords, links, and ingest runs.
"""

from __future__ import annotations

import json
import logging
import sqlite3
from pathlib import Path
from typing import Any, Dict, List, Optional
from src.edocs.models import Chunk, Document, FieldRecord, IngestStats

logger = logging.getLogger("edocs.store.pg")


def ensure_sqlite_database(sqlite_path: Path):
    gz_path = sqlite_path.with_suffix(sqlite_path.suffix + ".gz")
    # If uncompressed database is missing or smaller than 10MB (empty schema), unpack from .gz
    if gz_path.exists() and (not sqlite_path.exists() or sqlite_path.stat().st_size < 10000000):
        import gzip
        import shutil
        sqlite_path.parent.mkdir(parents=True, exist_ok=True)
        logger.info("Unpacking compressed database from %s to %s...", gz_path, sqlite_path)
        with gzip.open(gz_path, "rb") as f_in, open(sqlite_path, "wb") as f_out:
            shutil.copyfileobj(f_in, f_out)
        logger.info("Successfully unpacked database: %d bytes", sqlite_path.stat().st_size)


class PostgresStore:
    def __init__(self, dsn: str, sqlite_fallback_path: Path | None = None):
        self.dsn = dsn
        self.sqlite_fallback_path = sqlite_fallback_path or Path("data/edocs.db")
        ensure_sqlite_database(self.sqlite_fallback_path)
        self.use_sqlite = False
        self._init_connection()

    def _init_connection(self):
        # Check if psycopg2 or asyncpg can connect to Postgres
        try:
            import psycopg2
            conn = psycopg2.connect(self.dsn, connect_timeout=2)
            conn.close()
            logger.info("Connected to PostgreSQL at %s", self.dsn)
            self.use_sqlite = False
        except Exception as e:
            logger.warning(
                "PostgreSQL connection to %s unavailable (%s). Falling back to local SQLite at %s",
                self.dsn,
                e,
                self.sqlite_fallback_path,
            )
            self.use_sqlite = True
            self._init_sqlite()

    def _init_sqlite(self):
        self.sqlite_fallback_path.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(self.sqlite_fallback_path) as conn:
            cur = conn.cursor()
            cur.execute("""
            CREATE TABLE IF NOT EXISTS documents (
                doc_id TEXT PRIMARY KEY,
                release TEXT NOT NULL,
                chm TEXT NOT NULL,
                path TEXT NOT NULL,
                title TEXT NOT NULL,
                breadcrumbs TEXT NOT NULL,
                toc_order INTEGER,
                topic_type TEXT NOT NULL,
                product_area TEXT NOT NULL,
                summary TEXT,
                markdown TEXT NOT NULL,
                images TEXT NOT NULL,
                also_in TEXT NOT NULL,
                orphan INTEGER NOT NULL,
                content_hash TEXT NOT NULL
            );
            """)
            cur.execute("""
            CREATE TABLE IF NOT EXISTS chunks (
                chunk_id TEXT PRIMARY KEY,
                doc_id TEXT NOT NULL,
                release TEXT NOT NULL,
                text TEXT NOT NULL,
                section_path TEXT NOT NULL,
                anchor TEXT,
                topic_type TEXT NOT NULL,
                product_area TEXT NOT NULL,
                kind TEXT NOT NULL,
                token_count INTEGER NOT NULL,
                content_hash TEXT NOT NULL
            );
            """)
            cur.execute("""
            CREATE TABLE IF NOT EXISTS fields (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                release TEXT NOT NULL,
                record TEXT NOT NULL,
                field_name TEXT NOT NULL,
                field_number TEXT,
                poweron_mnemonic TEXT,
                symxchange_mnemonic TEXT,
                data_type TEXT,
                source TEXT,
                help_file TEXT,
                default_control TEXT,
                default_value TEXT,
                description TEXT,
                doc_id TEXT NOT NULL
            );
            """)
            cur.execute("""
            CREATE TABLE IF NOT EXISTS keywords (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                release TEXT NOT NULL,
                term TEXT NOT NULL,
                doc_id TEXT NOT NULL
            );
            """)
            cur.execute("""
            CREATE TABLE IF NOT EXISTS ingest_runs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                release TEXT NOT NULL,
                chm_hashes TEXT NOT NULL,
                documents_count INTEGER NOT NULL,
                chunks_count INTEGER NOT NULL,
                fields_count INTEGER NOT NULL,
                links_count INTEGER NOT NULL,
                duration_seconds REAL NOT NULL,
                warnings TEXT NOT NULL,
                status TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
            """)
            conn.commit()

    def get_existing_chunk_hashes(self, release: str) -> Dict[str, str]:
        """Returns map of chunk_id -> content_hash for incremental re-indexing."""
        if self.use_sqlite:
            with sqlite3.connect(self.sqlite_fallback_path) as conn:
                cur = conn.cursor()
                cur.execute("SELECT chunk_id, content_hash FROM chunks WHERE release = ?", (release,))
                return dict(cur.fetchall())
        else:
            import psycopg2
            with psycopg2.connect(self.dsn) as conn:
                with conn.cursor() as cur:
                    cur.execute("SELECT chunk_id, content_hash FROM chunks WHERE release = %s;", (release,))
                    return dict(cur.fetchall())

    def upsert_chunks(self, chunks: List[Chunk]):
        if not chunks:
            return
        if self.use_sqlite:
            with sqlite3.connect(self.sqlite_fallback_path) as conn:
                cur = conn.cursor()
                for c in chunks:
                    cur.execute("""
                    INSERT INTO chunks (chunk_id, doc_id, release, text, section_path, anchor, topic_type, product_area, kind, token_count, content_hash)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(chunk_id) DO UPDATE SET
                        text=excluded.text,
                        section_path=excluded.section_path,
                        token_count=excluded.token_count,
                        content_hash=excluded.content_hash
                    """, (
                        c.chunk_id, c.doc_id, c.release, c.text,
                        json.dumps(c.section_path), c.anchor, c.topic_type,
                        c.product_area, c.kind, c.token_count, c.content_hash
                    ))
                conn.commit()

    def upsert_documents(self, docs: List[Document]):
        if not docs:
            return
        if self.use_sqlite:
            with sqlite3.connect(self.sqlite_fallback_path) as conn:
                cur = conn.cursor()
                for d in docs:
                    cur.execute("""
                    INSERT INTO documents (doc_id, release, chm, path, title, breadcrumbs, toc_order, topic_type, product_area, summary, markdown, images, also_in, orphan, content_hash)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(doc_id) DO UPDATE SET
                        title=excluded.title,
                        breadcrumbs=excluded.breadcrumbs,
                        markdown=excluded.markdown,
                        content_hash=excluded.content_hash
                    """, (
                        d.doc_id, d.release, d.chm, d.path, d.title,
                        json.dumps(d.breadcrumbs), d.toc_order, d.topic_type,
                        d.product_area, d.summary, d.markdown,
                        json.dumps(d.images), json.dumps(d.also_in),
                        1 if d.orphan else 0, d.content_hash
                    ))
                conn.commit()

    def upsert_fields(self, fields: List[FieldRecord]):
        if not fields:
            return
        if self.use_sqlite:
            with sqlite3.connect(self.sqlite_fallback_path) as conn:
                cur = conn.cursor()
                cur.execute("DELETE FROM fields;")
                rows = [
                    (
                        f.release, f.record, f.field_name, f.field_number,
                        f.poweron_mnemonic, f.symxchange_mnemonic, f.data_type,
                        f.source, f.help_file, f.default_control, f.default_value,
                        f.description, f.doc_id
                    )
                    for f in fields
                ]
                cur.executemany("""
                INSERT INTO fields (release, record, field_name, field_number, poweron_mnemonic, symxchange_mnemonic, data_type, source, help_file, default_control, default_value, description, doc_id)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, rows)
                conn.commit()

    def upsert_keywords(self, keywords: List[Dict[str, Any]]):
        if not keywords:
            return
        if self.use_sqlite:
            with sqlite3.connect(self.sqlite_fallback_path) as conn:
                cur = conn.cursor()
                for k in keywords:
                    cur.execute("""
                    INSERT INTO keywords (release, term, doc_id)
                    VALUES (?, ?, ?)
                    """, (k["release"], k["term"], k["doc_id"]))
                conn.commit()
        else:
            import psycopg2.extras
            with psycopg2.connect(self.dsn) as conn:
                with conn.cursor() as cur:
                    psycopg2.extras.execute_batch(
                        cur,
                        """
                        INSERT INTO keywords (release, term, doc_id)
                        VALUES (%(release)s, %(term)s, %(doc_id)s)
                        """,
                        keywords,
                    )
                conn.commit()

    def search_fields(
        self, query: str, record: Optional[str] = None, release: str = "2023.00", limit: int = 10
    ) -> List[FieldRecord]:
        q = query.strip()
        results: List[FieldRecord] = []
        if self.use_sqlite:
            with sqlite3.connect(self.sqlite_fallback_path) as conn:
                cur = conn.cursor()
                sql = """
                SELECT release, record, field_name, field_number, poweron_mnemonic, symxchange_mnemonic, data_type, source, help_file, default_control, default_value, description, doc_id
                FROM fields
                WHERE release = ? AND (
                    upper(record) = upper(?) OR
                    record LIKE ? OR
                    poweron_mnemonic LIKE ? OR
                    field_name LIKE ? OR
                    field_number LIKE ?
                )
                """
                params = [release, q, f"%{q}%", f"%{q}%", f"%{q}%", f"%{q}%"]
                if record:
                    sql += " AND (upper(record) = upper(?) OR record LIKE ?)"
                    params.extend([record, f"%{record}%"])
                sql += """
                ORDER BY
                    CASE WHEN upper(record) = upper(?) THEN 1
                         WHEN upper(poweron_mnemonic) = upper(?) THEN 2
                         WHEN upper(field_name) = upper(?) THEN 3
                         ELSE 4 END,
                    id ASC
                LIMIT ?
                """
                params.extend([q, q, q, limit])
                cur.execute(sql, params)
                for r in cur.fetchall():
                    results.append(
                        FieldRecord(
                            release=r[0], record=r[1], field_name=r[2],
                            field_number=r[3], poweron_mnemonic=r[4],
                            symxchange_mnemonic=r[5], data_type=r[6],
                            source=r[7], help_file=r[8], default_control=r[9],
                            default_value=r[10], description=r[11], doc_id=r[12],
                        )
                    )
        return results

    def record_ingest_run(self, stats: IngestStats):
        if self.use_sqlite:
            with sqlite3.connect(self.sqlite_fallback_path) as conn:
                cur = conn.cursor()
                cur.execute("""
                INSERT INTO ingest_runs (release, chm_hashes, documents_count, chunks_count, fields_count, links_count, duration_seconds, warnings, status)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    stats.release, json.dumps(stats.chm_hashes), stats.documents_count,
                    stats.chunks_count, stats.fields_count, stats.links_count,
                    stats.duration_seconds, json.dumps(stats.warnings), "completed"
                ))
                conn.commit()
