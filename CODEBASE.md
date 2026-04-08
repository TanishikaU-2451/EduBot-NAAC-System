# Codebase Guide — NAAC Compliance Intelligence System

This document is a developer-facing walkthrough of the repository. It explains the directory layout, the role of every module, how data flows through the system end-to-end, and how to extend or modify each layer. Read the top-level [README.md](README.md) first for setup and usage instructions.

---

## Table of Contents

1. [High-Level Architecture](#1-high-level-architecture)
2. [Repository Layout](#2-repository-layout)
3. [Backend — Module by Module](#3-backend--module-by-module)
   - [config/](#31-config)
   - [api/](#32-api)
   - [ingestion/](#33-ingestion)
   - [db/](#34-db)
   - [rag/](#35-rag)
   - [llm/](#36-llm)
   - [memory/](#37-memory)
   - [scheduler/](#38-scheduler)
   - [updater/](#39-updater)
   - [auth/](#310-auth)
   - [debug/](#311-debug)
4. [Frontend — Module by Module](#4-frontend--module-by-module)
5. [End-to-End Data Flows](#5-end-to-end-data-flows)
   - [Document Ingestion Flow](#51-document-ingestion-flow)
   - [Query / Chat Flow](#52-query--chat-flow)
   - [Scheduled Auto-Update Flow](#53-scheduled-auto-update-flow)
6. [Database Schema](#6-database-schema)
7. [Configuration Reference](#7-configuration-reference)
8. [Testing](#8-testing)
9. [How to Extend the System](#9-how-to-extend-the-system)

---

## 1. High-Level Architecture

```
┌─────────────────────────────────────────┐
│           Browser / Client              │
│      React 18 + TypeScript + MUI        │
└───────────────────┬─────────────────────┘
                    │ HTTP/REST (Axios)
                    ▼
┌─────────────────────────────────────────┐
│         FastAPI Backend (Python)        │
│  api/main.py — single entry point       │
│                                         │
│  ┌──────────┐  ┌──────────┐  ┌───────┐ │
│  │Ingestion │  │RAG       │  │Auth / │ │
│  │Pipeline  │  │Pipeline  │  │Sched  │ │
│  └────┬─────┘  └────┬─────┘  └───────┘ │
└───────┼─────────────┼───────────────────┘
        │             │
        ▼             ▼
┌───────────────┐   ┌──────────────────────┐
│ Vector Store  │   │   Groq LLM API       │
│ (Supabase /   │   │  llama-3.3-70b       │
│  Chroma /     │   │  (remote inference)  │
│  Local)       │   └──────────────────────┘
│ pgvector 384d │
└───────────────┘
```

The system has three distinct concerns:

| Layer | Technology | Purpose |
|-------|-----------|---------|
| **Presentation** | React + Material-UI | Chat UI, document upload, system dashboard, scheduler management |
| **Application** | FastAPI + Python | REST API, RAG pipeline, ingestion, scheduling, authentication |
| **Data** | Supabase PostgreSQL + pgvector | Persistent vector storage; Groq API for LLM inference |

---

## 2. Repository Layout

```
EduBot-NAAC-System/
├── README.md                  # Setup & usage documentation
├── CODEBASE.md                # This file — developer guide
├── requirements.txt           # Python dependencies
├── .env.example               # Template for environment configuration
├── db_schema.txt              # SQL DDL for Supabase (run once to provision)
├── ingestion_log.json         # Generated when PERSIST_INGESTION_LOG=true; tracks ingested files
│
├── backend/                   # All Python source code
│   ├── __init__.py
│   ├── run_server.py          # Convenience entry point (wraps uvicorn)
│   ├── api/                   # FastAPI application & route handlers
│   ├── auth/                  # Token-based authentication
│   ├── config/                # Pydantic settings (reads .env)
│   ├── db/                    # Vector store adapters
│   ├── debug/                 # Pipeline tracing utilities
│   ├── ingestion/             # PDF loading, chunking, deduplication
│   ├── llm/                   # Groq client & prompt utilities
│   ├── memory/                # Conversation memory store
│   ├── rag/                   # Retriever, generator, reranker, pipeline
│   ├── scheduler/             # APScheduler job management
│   └── updater/               # NAAC website monitoring & auto-ingest
│
├── frontend/                  # React TypeScript application
│   ├── package.json
│   ├── public/
│   └── src/
│       ├── App.tsx
│       ├── components/        # Page-level React components
│       ├── contexts/          # React context providers
│       ├── services/          # Axios API wrapper
│       ├── types/             # TypeScript interfaces
│       └── setupProxy.js      # CRA dev proxy → backend :8000
│
└── tests/                     # Python unit tests (pytest)
    ├── test_prompt_utils.py
    └── test_retrieval_and_generation.py
```

---

## 3. Backend — Module by Module

### 3.1 `config/`

**File**: `backend/config/settings.py`

Centralises all runtime configuration using **Pydantic Settings** (`pydantic-settings`). The `Settings` class reads values from environment variables and `.env` files automatically. A global singleton `settings` is imported by every other module:

```python
from ..config.settings import settings
```

Key setting groups:

| Group | Notable fields |
|-------|---------------|
| App | `app_name`, `debug`, `host`, `port` |
| Vector store | `vector_backend`, `supabase_db_url`, `supabase_table`, `embedding_dim` |
| LLM | `groq_api_key`, `groq_model`, `groq_timeout` |
| Embeddings | `embedding_model`, `embedding_device`, `embedding_batch_size` |
| Chunking | `chunk_size`, `chunk_overlap`, `min_chunk_length` |
| Retrieval | `max_retrieval_results`, `similarity_threshold`, `retrieval_mode`, `retrieval_dense_weight` |
| Reranker | `reranker_enabled`, `reranker_model` |
| Scheduler | `job_store_url` (SQLite path) |
| Memory | `memory_enabled`, `memory_short_ttl_days`, `memory_long_ttl_days` |
| Security | `api_key`, `cors_origins`, `rate_limit_requests` |

There are also two environment-specific subclasses (`DevelopmentSettings`, `ProductionSettings`) and a `get_settings()` factory that selects the right class based on the `ENVIRONMENT` env var.

---

### 3.2 `api/`

**File**: `backend/api/main.py`

The single FastAPI application. It:

1. Creates the `FastAPI` app instance with CORS and optional API-key middleware.
2. Initialises all shared singletons on startup: vector store, embedding model, Groq client, RAG pipeline, scheduler, and memory store.
3. Defines all HTTP routes.

**Route groups**

| Prefix | Purpose |
|--------|---------|
| `POST /api/auth/login` | Returns a session token |
| `POST /api/auth/logout` | Invalidates session |
| `GET  /api/auth/me` | Returns current session info |
| `POST /api/query` | Main RAG query endpoint |
| `POST /api/upload` | Stage an uploaded PDF in memory |
| `DELETE /api/upload` | Remove a staged upload |
| `POST /api/ingest` | Ingest all staged documents |
| `POST /api/ingest/status` | Progress of ongoing ingestion |
| `GET  /api/health` | Component health check |
| `GET  /api/db/health` | Vector store connectivity |
| `GET  /api/stats` | Pipeline & update statistics |
| `POST /api/force-update` | Trigger manual NAAC scrape |
| `GET  /api/last-sync` | Timestamp of last auto-update |
| `GET  /api/scheduler/status` | All scheduled jobs |
| `POST /api/scheduler/schedule` | Create a scheduled job |
| `POST /api/scheduler/jobs/{id}/pause` | Pause a job |
| `POST /api/scheduler/jobs/{id}/resume` | Resume a job |
| `DELETE /api/scheduler/jobs/{id}` | Remove a job |
| `GET  /api/mapping/analyze` | Map a query to NAAC criteria |

**Dependency injection**: FastAPI's `Depends()` is used for the optional API-key guard. The shared singletons (pipeline, scheduler, store) are module-level globals initialised in the `startup` event handler.

---

### 3.3 `ingestion/`

Responsible for converting raw PDF files into searchable vector chunks.

| File | Class / Function | Role |
|------|-----------------|------|
| `pdf_loader.py` | `PDFLoader` | Extracts raw text from PDFs using `pdfplumber` (primary), `pypdf2` and `pdfminer.six` as fallbacks. Selects strategy via `PDF_EXTRACTION_STRATEGY` setting. |
| `chunker.py` | `DocumentChunker` | Splits extracted text into overlapping chunks. Uses separate size/overlap values for large documents (>120 pages). Enforces `min_chunk_length` to skip noise. |
| `ingest.py` | `DocumentIngester` | Orchestrates the full pipeline: load → clean → chunk → embed → deduplicate → upsert. Maintains an optional in-memory (or JSON) ingestion log to skip already-processed files. |

**Deduplication** is done via a SHA-256 hash of each chunk's text, stored in the ingestion log. Re-ingesting the same document is idempotent.

---

### 3.4 `db/`

Provides a unified interface for all vector store backends. The active backend is selected by `VECTOR_BACKEND`.

| File | Class | Backend |
|------|-------|---------|
| `supabase_store.py` | `SupabaseVectorStore` | **Default**. PostgreSQL + pgvector. Supports hybrid (dense + lexical) retrieval via cosine similarity and `ts_rank`. |
| `chroma_store.py` | `ChromaVectorStore` | Local ChromaDB. Good for development without a Supabase project. |
| `local_store.py` | `LocalVectorStore` | Pure in-memory numpy store. No persistence. Useful for testing. |

All three implement the same informal protocol with methods:
- `query_naac_requirements(query_text, n_results, criterion_filter)` → `Dict`
- `query_mvsr_evidence(query_text, n_results, category_filter)` → `Dict`
- `add_documents(documents, metadatas, doc_type)` → `None`

The `doc_type` metadata field (`"naac_requirement"` vs `"mvsr_evidence"`) is how the store separates the two knowledge bases within a single `chunks` table.

**Hybrid retrieval** (Supabase only): combines a pgvector cosine-similarity score (weight `RETRIEVAL_DENSE_WEIGHT`) with a full-text `ts_rank` score (weight `RETRIEVAL_LEXICAL_WEIGHT`). Results below `SIMILARITY_THRESHOLD` are discarded unless a threshold-fallback is triggered.

---

### 3.5 `rag/`

The core intelligence layer — three specialised classes wired together by the pipeline.

#### `retriever.py` — `ComplianceRetriever`

Queries both knowledge bases in parallel and returns two `RetrievalResult` dataclasses (one NAAC, one MVSR). Applies threshold filtering and optionally falls back to the top-k results when nothing passes the threshold.

#### `reranker.py` — `ComplianceReranker`

Optional cross-encoder re-ranking step that sits between retrieval and generation. Uses `cross-encoder/ms-marco-MiniLM-L-6-v2` (via `sentence-transformers`) to re-score chunks against the query and keeps only the highest-scoring ones. Controlled by `RERANKER_ENABLED`.

#### `generator.py` — `ComplianceGenerator`

Builds a structured prompt from the retrieved chunks and calls `GroqClient`. Parses the LLM response into a structured dict containing:
- `compliance_analysis` — narrative analysis
- `status` — one of `COMPLIANT`, `PARTIAL`, `NON_COMPLIANT`, `INSUFFICIENT_DATA`
- `recommendations` — list of actionable items
- `confidence_score` — 0–1 float
- `sources` — document references

#### `metadata_mapper.py` — `MetadataMapper`

Inspects the query and retrieved chunk metadata to infer which NAAC criterion (1–7) is most relevant. The mapping enriches the generated response with criterion tags.

#### `pipeline.py` — `RAGPipeline`

Orchestrator class that calls all of the above in order:

```
User query
  → extract_query_context()   # classify query type, extract filters
  → ComplianceRetriever       # dual retrieval (NAAC + MVSR)
  → ComplianceReranker        # optional re-ranking
  → ComplianceGenerator       # LLM generation
  → format_response()         # merge + enrich response
  → (optionally) memory store # save turn to conversation history
```

**Query types** detected: `general`, `direct_question`, `criterion_specific`, `evidence_lookup`, `gap_analysis`. The type influences retrieval weights and prompt templates.

---

### 3.6 `llm/`

| File | Class / Function | Role |
|------|-----------------|------|
| `groq_client.py` | `GroqClient` | Thin wrapper around `groq` Python SDK. Handles retries, timeouts, and error logging. |
| `prompt_utils.py` | Various helpers | Builds prompt strings from templates, parses LLM response tags (`<compliance_analysis>`, `<status>`, etc.), and cleans output. |

Prompt templates live entirely inside `prompt_utils.py`. To change the system prompt or add new response tags, edit only this file.

---

### 3.7 `memory/`

**File**: `backend/memory/memory_store.py` — `MemoryStore`

Stores recent conversation turns in an in-memory dict keyed by `session_id`. Each turn holds the user query and the assistant response. Two TTL tiers:

| Tier | TTL | Limit | Used for |
|------|-----|-------|---------|
| Short-term | `MEMORY_SHORT_TTL_DAYS` (7) | `MEMORY_SHORT_LIMIT` (20) turns | Injected verbatim into the current prompt |
| Long-term | `MEMORY_LONG_TTL_DAYS` (365) | Top `MEMORY_LONG_TOP_K` (6) turns by embedding similarity | Provides broader context for follow-up queries |

Memory is purely in-process — it resets when the server restarts. Enable a persistent backend by swapping `MemoryStore` for a DB-backed implementation.

---

### 3.8 `scheduler/`

**File**: `backend/scheduler/update_scheduler.py` — `UpdateScheduler`

Wraps **APScheduler** (`BackgroundScheduler` with a SQLite job store at `JOB_STORE_URL`). Exposes methods called by the API:

| Method | Description |
|--------|-------------|
| `add_daily_job(hour, minute)` | Run every day at a fixed time |
| `add_interval_job(hours)` | Run every N hours |
| `add_criterion_job(criterion, hours)` | Run targeting a specific NAAC criterion |
| `pause_job(job_id)` | Suspend a job |
| `resume_job(job_id)` | Restart a suspended job |
| `remove_job(job_id)` | Delete a job |
| `get_all_jobs()` | List jobs with status |

Each job calls the `updater` module to check for new NAAC documents.

---

### 3.9 `updater/`

**File**: `backend/updater/auto_ingest.py` — `AutoIngestor`

Responsible for keeping the knowledge base current:

1. Scrapes `NAAC_BASE_URL` using **BeautifulSoup4** to find links to new PDFs.
2. Compares discovered URLs against the ingestion log.
3. Downloads new PDFs and passes them through the `DocumentIngester` pipeline.
4. Updates the `last_sync` timestamp.

`AUTO_INGEST_ENABLED=false` by default — the scraping runs only when explicitly triggered (via the scheduler or `POST /api/force-update`).

---

### 3.10 `auth/`

**File**: `backend/auth/auth.py`

Lightweight token-based auth for the API. On `POST /api/auth/login`, a random token is generated and stored in memory. Subsequent requests that include this token in the `Authorization: Bearer <token>` header are considered authenticated.

> **Note**: The auth layer is intentionally minimal. For production use, replace with a proper OAuth2 / JWT implementation.

---

### 3.11 `debug/`

**File**: `backend/debug/trace_logger.py` — `PipelineTraceLogger`

When `PIPELINE_DEBUG_ENABLED=true`, each query is assigned a `debug_trace_id` and detailed step-level logs are written to `PIPELINE_DEBUG_DIR`. This includes the raw retrieved chunks, the constructed prompt, and the raw LLM response — useful for diagnosing retrieval or generation issues.

---

## 4. Frontend — Module by Module

The React application is a standard **Create React App** project written in TypeScript.

```
frontend/src/
├── App.tsx                  # Root component; sets up routes and theme
├── index.tsx                # ReactDOM.render entry point
├── index.css                # Global Tailwind base styles
├── setupProxy.js            # Dev proxy: /api/* → http://localhost:8000
│
├── components/
│   ├── Login.tsx            # Authentication form
│   ├── layout/
│   │   └── Layout.tsx       # Nav bar + page shell
│   ├── chat/
│   │   └── ChatInterface.tsx  # Main query UI; sends POST /api/query
│   ├── upload/
│   │   └── DocumentUpload.tsx # Drag-and-drop PDF upload
│   ├── dashboard/
│   │   └── SystemDashboard.tsx # Health, stats, last-sync
│   └── scheduler/
│       └── SchedulerManager.tsx # Create / pause / resume jobs
│
├── contexts/
│   └── AuthContext.tsx      # Provides current user + login/logout helpers
│
├── services/
│   └── api.ts               # Axios instance with base URL + interceptors
│
└── types/
    └── index.ts             # TypeScript interfaces for all API payloads
```

**Navigation** is handled by React Router v6. Each page corresponds to one top-level component under `components/`. The `Layout` component renders the nav bar and wraps all routes.

**API communication** is entirely handled by `services/api.ts`. Every component imports only the functions it needs from there — not Axios directly. This makes it easy to mock the API in tests.

**State management** is kept simple: component-local `useState`/`useEffect` hooks plus the `AuthContext`. There is no Redux or other global state library.

---

## 5. End-to-End Data Flows

### 5.1 Document Ingestion Flow

```
User selects PDF file(s) in DocumentUpload.tsx
  │
  ▼ POST /api/upload (multipart/form-data)
api/main.py → stores file bytes in memory staging area
  │
  ▼ POST /api/ingest
api/main.py
  → DocumentIngester.ingest(staged_files)
      → PDFLoader.load(bytes)         # extract raw text
      → DocumentChunker.chunk(text)   # split into overlapping chunks
      → EmbeddingModel.encode(chunks) # 384-dim vectors (all-MiniLM-L6-v2)
      → deduplication check           # skip already-ingested chunks
      → VectorStore.add_documents()   # upsert to Supabase/Chroma/Local
      → update ingestion log
  ◄── returns { ingested_count, skipped_count, errors }
```

### 5.2 Query / Chat Flow

```
User types a message in ChatInterface.tsx
  │
  ▼ POST /api/query { query, session_id, filters? }
api/main.py
  → RAGPipeline.query(query, session_id)
      → extract_query_context()            # classify query type
      → MemoryStore.get_history(session_id)# retrieve conversation context
      → ComplianceRetriever
          → VectorStore.query_naac_requirements()  # top-k NAAC chunks
          → VectorStore.query_mvsr_evidence()      # top-k MVSR chunks
      → ComplianceReranker (if enabled)    # cross-encoder re-ranking
      → ComplianceGenerator
          → build_prompt(context, history) # assemble prompt
          → GroqClient.chat(prompt)        # call Groq LLM
          → parse_response(raw)            # extract structured fields
      → MetadataMapper.map_criteria()      # tag relevant NAAC criteria
      → MemoryStore.save_turn(session_id)  # persist for next turn
  ◄── returns structured response JSON
ChatInterface.tsx renders response with react-markdown
```

### 5.3 Scheduled Auto-Update Flow

```
APScheduler fires a job (daily / interval / criterion)
  │
  ▼ UpdateScheduler calls AutoIngestor.run()
      → HTTP GET NAAC_BASE_URL             # scrape NAAC website
      → BeautifulSoup4 parses PDF links
      → compare with ingestion log         # find new documents
      → for each new PDF:
          → HTTP GET pdf_url               # download
          → DocumentIngester.ingest()      # full ingestion pipeline
      → update last_sync timestamp
  ◄── logs result; updates /api/stats
```

---

## 6. Database Schema

The entire vector store is a single PostgreSQL table (see `db_schema.txt`):

```sql
CREATE TABLE public.chunks (
    id         UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    doc_type   TEXT        NOT NULL,   -- 'naac_requirement' | 'mvsr_evidence'
    content    TEXT        NOT NULL,   -- raw chunk text
    metadata   JSONB       NOT NULL,   -- criterion, category, source_file, …
    embedding  vector(384) NOT NULL,   -- all-MiniLM-L6-v2 output
    created_at TIMESTAMPTZ DEFAULT now()
);

-- Vector similarity index
CREATE INDEX chunks_embedding_idx
    ON public.chunks USING ivfflat (embedding vector_cosine_ops)
    WITH (lists = 100);

-- Metadata indexes for filtered retrieval
CREATE INDEX chunks_doc_type_idx ON public.chunks (doc_type);
CREATE INDEX chunks_criterion_idx ON public.chunks ((metadata->>'criterion'));
CREATE INDEX chunks_category_idx  ON public.chunks ((metadata->>'category'));
```

Key metadata fields stored in the `metadata` JSONB column:

| Field | Example values | Used for |
|-------|---------------|---------|
| `criterion` | `"1"` … `"7"` | Filtering NAAC criteria |
| `category` | `"curriculum"`, `"faculty"` | Filtering MVSR evidence |
| `section_header` | `"1.1 Curricular Design"` | Display in citations |
| `source_file` | `"naac_manual_2023.pdf"` | Provenance tracking |
| `chunk_index` | `0`, `1`, `2` … | Ordering within document |

---

## 7. Configuration Reference

All settings are read from `.env` (or environment variables). Copy `.env.example` to `.env` and fill in the required values. See `backend/config/settings.py` for the full list with defaults.

**Required for a working system**:

```env
SUPABASE_DB_URL=postgresql://user:password@host:5432/postgres
GROQ_API_KEY=gsk_...
```

**Commonly tuned**:

```env
# Retrieval quality vs speed
MAX_RETRIEVAL_RESULTS=10          # increase for more context
SIMILARITY_THRESHOLD=0.3          # lower = more results, higher = more precise
RERANKER_ENABLED=true             # disable to reduce latency

# Chunking (affects re-ingestion required after change)
CHUNK_SIZE=1000
CHUNK_OVERLAP=200

# Vector backend (supabase | chroma | local)
VECTOR_BACKEND=supabase
```

---

## 8. Testing

Tests live in the top-level `tests/` directory and use **pytest**.

| File | What it tests |
|------|--------------|
| `test_prompt_utils.py` | LLM response parsing: tag extraction, status detection, structure preservation |
| `test_retrieval_and_generation.py` | Retrieval pipeline with a stub vector store; threshold fallback logic; metadata preservation |

Run all tests:

```bash
pytest tests/
```

The tests use lightweight stubs and do not require a live Supabase or Groq connection.

---

## 9. How to Extend the System

### Add a new vector store backend

1. Create `backend/db/my_store.py` implementing `query_naac_requirements`, `query_mvsr_evidence`, and `add_documents`.
2. Register the new key in `api/main.py` where the backend is selected by `settings.vector_backend`.
3. Add any required settings to `config/settings.py`.

### Change the LLM

1. Edit `backend/llm/groq_client.py` to swap the SDK or model.
2. Update prompt templates in `backend/llm/prompt_utils.py` if the response format changes.
3. Update `GroqClient` references in `generator.py` if the call signature changes.

### Add a new API endpoint

1. Add a Pydantic request/response model near the top of `api/main.py`.
2. Add the `@app.get` / `@app.post` route handler.
3. Add a corresponding function in `frontend/src/services/api.ts`.
4. Add the TypeScript types to `frontend/src/types/index.ts`.

### Change chunking strategy

Edit `backend/ingestion/chunker.py`. The `DocumentChunker` class exposes `chunk_size`, `chunk_overlap`, and `min_chunk_length` as constructor arguments (pulled from settings). Override them or add new splitting logic there.

### Add a new scheduled job type

1. Add a method to `backend/scheduler/update_scheduler.py` following the pattern of `add_daily_job`.
2. Expose it via a new route in `api/main.py`.
3. Add the corresponding UI controls to `frontend/src/components/scheduler/SchedulerManager.tsx`.

---

*For setup, environment configuration, and usage examples, see [README.md](README.md).*
