# Operations Runbook — Symitar eDocs Assistant

This runbook covers administration, deployment, maintenance, and incident recovery for the Symitar eDocs assistant.

---

## 1. Initial Installation & Quickstart

### Prerequisites
- Docker Engine 24+ and Docker Compose v2+
- Python 3.10+ (for local development)
- (Optional) NVIDIA GPU with 16GB+ VRAM if running local LLM/embeddings in production

### Starting the System
1. Clone the repository and configure `.env`:
   ```bash
   cp .env.example .env
   # Edit .env with your GROQ_API_KEY or local Ollama URL
   ```
2. Start the services:
   ```bash
   docker compose up -d
   ```
3. Check system health:
   ```bash
   curl http://localhost:8000/healthz
   curl http://localhost:8000/readyz
   ```
4. Access the Reference Web UI:
   Open `http://localhost:8000` in your browser.

---

## 2. Ingesting a New eDocs Release

When a new Symitar Episys `.chm` file is released (e.g. `2024.01`):

1. **Place source CHM in raw data folder**:
   ```bash
   cp /path/to/eDocs_2024.01.chm data/raw/
   ```
2. **Phase 1 — Run Discovery Inventory**:
   ```bash
   python -m src.edocs.ingest.inventory data/raw/eDocs_2024.01.chm --release 2024.01
   ```
   Inspect `docs/inventory_2024.01.md` and verify topic types, table labels, and counts.
3. **Phase 2 — Run Parsing Pipeline**:
   ```bash
   python -m src.edocs.ingest.pipeline data/extracted/2024.01/edocs --release 2024.01
   ```
4. **Phase 3 — Run Chunking & Indexing**:
   ```bash
   python -m src.edocs.ingest.index_corpus --release 2024.01
   ```
   *Note*: The incremental indexer will embed only new or modified topics, skipping identical documentation.

---

## 3. Switching Default Release

To promote a newly ingested release to be the default for user queries:
1. Update `config/settings.yaml`:
   ```yaml
   app:
     default_release: "2024.01"
   ```
2. Or set `DEFAULT_RELEASE=2024.01` in `.env` and restart the API container:
   ```bash
   docker compose restart api
   ```

---

## 4. Backups and Disaster Recovery

### PostgreSQL Database
- **Backup**:
  ```bash
  docker compose exec postgres pg_dump -U edocs edocs > backup_edocs_$(date +%Y%m%d).sql
  ```
- **Restore**:
  ```bash
  docker compose exec -T postgres psql -U edocs edocs < backup_edocs_20261016.sql
  ```

### Qdrant Vector Store
- **Snapshot creation**:
  ```bash
  curl -X POST "http://localhost:6333/collections/edocs_chunks/snapshots"
  ```
- **Restore snapshot**:
  ```bash
  curl -X POST "http://localhost:6333/collections/edocs_chunks/snapshots/upload" \
       -H "Content-Type:multipart/form-data" \
       -F "snapshot=@snapshot-name.snapshot"
  ```

---

## 5. Offline Operation & Model Deployment

For disconnected / air-gapped banking servers:
1. Pre-pull the embedding model (`BAAI/bge-m3`) and reranker (`BAAI/bge-reranker-v2-m3`) onto a workstation:
   ```bash
   huggingface-cli download BAAI/bge-m3 --local-dir model_cache/bge-m3
   huggingface-cli download BAAI/bge-reranker-v2-m3 --local-dir model_cache/bge-reranker
   ```
2. Pre-pull Ollama image and model:
   ```bash
   ollama pull qwen2.5:14b-instruct
   ```
3. Set `HOSTED_LLM_ENABLED=false` in `.env`.

---

## 6. Outage Fallback Behavior

If the upstream LLM service or local model server is down:
- The `LLMClient` catches the timeout / unreachable error.
- The assistant falls back to **extractive synthesis**: it retrieves the top-1 ranked excerpt directly from the eDocs index, outputs the direct documentation text, attaches source citations `[1]`, and displays links to open the original page in the viewer.
- Staff can always access verified documentation even during LLM outages.
