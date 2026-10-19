---
title: Symitar eDocs Assistant
emoji: 🏦
colorFrom: indigo
colorTo: blue
sdk: docker
app_port: 7860
pinned: false
---

# Symitar eDocs Assistant

A production-grade, local-first Retrieval-Augmented Generation (RAG) assistant for **Jack Henry Symitar Episys eDocs** compiled HTML Help (`.chm`) documentation.

---

## Key Capabilities

- **Strict Domain Lock**: Answers questions strictly using indexed Symitar eDocs; out-of-domain queries trigger a fixed refusal.
- **Fact Grounding & Verbatim Identifiers**: Every answer is grounded with numbered citations `[n]` linking directly to the original documentation pages in the built-in document viewer. PowerOn mnemonics and field numbers are verified verbatim.
- **PII Protection**: Custom regex and Luhn algorithms automatically mask account numbers, SSNs, credit cards, phones, and emails prior to ingestion or logging.
- **Hybrid Retrieval**: Combines exact mnemonic lookup, dense/sparse semantic retrieval, Reciprocal Rank Fusion (RRF), and Cross-Encoder reranking (`BAAI/bge-reranker-v2-m3`).
- **Flexible Serving**: Swappable OpenAI-compatible LLM backend supporting local Ollama/vLLM or Groq cloud inference (`qwen/qwen3.8-27b`).
- **Reference Web Application**: Modern glassmorphic web interface with SSE streaming markdown and an embedded topic viewer drawer.

---

## Architecture Overview

```
                      ┌─────────────── INGESTION PIPELINE ───────────────┐
  eDocs.chm ──► extract ──► inventory ──► TOC (.hhc) ──► clean HTML ──► Markdown
                                                              │
                                                              ▼
                                                   structured fields & links
                                                              │
                                                              ▼
               Qdrant (chunks, hybrid vectors) ◄── chunker ──► PostgreSQL / SQLite

                      ┌──────────────── QUERY PIPELINE ────────────────┐
  User ──► PII Redaction ──► Rewrite ──► Intent Router ──► Exact + Hybrid Search
                                                                 │
                                                                 ▼
                                                  Cross-Encoder Reranker
                                                                 │
                                                                 ▼
                                                  Context Builder (XML Excerpts)
                                                                 │
                                                                 ▼
                                                    LLM (Ollama / vLLM / Groq)
                                                                 │
                                                                 ▼
                                                  Citation & Identifier Checks
                                                                 │
                                                                 ▼
                                                    SSE Stream to Reference UI
```

---

## Quickstart

### 1. Configuration
Copy `.env.example` to `.env`:
```bash
cp .env.example .env
```
Add your `GROQ_API_KEY` (or configure local Ollama).

### 2. Run Test Suite
Run all unit, integration, and contract tests:
```bash
python -m pytest tests -v
```

### 3. Interactive Chat CLI
Run the interactive terminal assistant:
```bash
python -m src.edocs.rag.chat
```

### 4. Start the Web Server & UI
Start the FastAPI server:
```bash
uvicorn src.edocs.api.app:app --reload --port 8000
```
Open [http://localhost:8000](http://localhost:8000) in your browser to view the reference application.

---

## API Endpoints

| Method | Endpoint | Description |
|---|---|---|
| `POST` | `/api/v1/chat` | Server-Sent Events (SSE) streaming chat completion |
| `GET` | `/api/v1/docs/{doc_id}` | Sanitised original HTML topic viewer |
| `GET` | `/api/v1/fields` | Instant field and mnemonic search panel |
| `GET` | `/api/v1/releases` | List available and default eDocs releases |
| `POST` | `/api/v1/feedback` | Record user thumbs up / down feedback |
| `GET` | `/healthz` | Liveness health check |
| `GET` | `/readyz` | Readiness health check |

---

## Project Structure

```
├── config/
│   ├── settings.yaml          # System configuration
│   ├── field_labels.yaml      # Normalized table label mapping
│   └── pii_patterns.yaml      # PII detection patterns
├── data/
│   ├── extracted/edocs/       # Extracted CHM content (7,038 topics, 2,392 images)
│   ├── processed/2023.00/     # JSONL datasets (documents, chunks, fields, links)
│   └── reports/               # Inventory and parsing reports
├── docs/
│   ├── inventory_2023.00.md   # Phase 1 Discovery report
│   ├── decisions.md           # Architecture decision log
│   ├── licenses.md            # Dependency licences
│   └── runbook.md             # Operations & maintenance guide
├── prompts/
│   ├── system_answer.md       # Grounded system prompt
│   ├── router.md              # Domain and intent classification
│   ├── rewrite.md             # Multi-turn query rewrite
│   └── templates.yaml         # Fixed refusal and not-found templates
├── src/edocs/
│   ├── api/                   # FastAPI routes, auth, and SSE
│   ├── ingest/                # Extraction, cleaning, fields, chunker, indexing
│   ├── llm/                   # OpenAI-compatible LLM client
│   ├── rag/                   # Router, gazetteer, retriever, context, postchecks
│   └── store/                 # PostgreSQL and Qdrant storage backends
├── tests/
│   ├── unit/                  # Unit tests for parsers, cleaners, and models
│   └── integration/           # Integration tests for pipeline and API contracts
└── web/
    └── reference.html         # Modern web application UI
```
