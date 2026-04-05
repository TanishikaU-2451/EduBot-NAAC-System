# NAAC Compliance Intelligence System

A sophisticated **Retrieval-Augmented Generation (RAG) platform** designed to understand NAAC requirements, retrieve MVSR institutional evidence, and map MVSR practices to NAAC criteria with automatic updates and semantic reasoning.

## Monorepo Layout

This project now uses a monorepo structure:

```
apps/
   backend/   # FastAPI, ingestion, retrieval, scheduler, updater
   web/       # React TypeScript frontend
api/         # Vercel Python function entrypoint (catch-all)
requirements.txt
vercel.json
```

Notes:
- Use `apps/backend` as the backend source root.
- Use `apps/web` as the frontend source root.
- Root `api/[...path].py` is used by Vercel to route backend API requests.

## 🎯 System Overview

This is **NOT a generic chatbot** but a specialized compliance intelligence system that:

- **Understands NAAC Requirements**: Processes official NAAC documentation and assessment criteria
- **Retrieves MVSR Evidence**: Searches institutional documents and evidence supporting compliance
- **Maps Practices to Criteria**: Creates intelligent connections between MVSR practices and NAAC standards
- **Automatic Updates**: Monitors NAAC website for new guidelines and updates knowledge base automatically 
- **Semantic Intelligence**: Uses embedding-based retrieval and LLM reasoning (no hardcoded mappings)

## 🏗️ Architecture

### Backend Components
- **FastAPI REST API (`apps/backend`)**: Orchestrates ingestion, retrieval, scheduling, and monitoring through HTTP endpoints
- **Supabase PostgreSQL + pgvector store**: Maintains NAAC requirements and MVSR evidence as aggregated vectors (see `db_schema.txt`) to support hybrid similarity search
- **Groq API**: Hosts the Llama 70B conversational model that generates structured compliance analysis
- **RAG Pipeline**: Combines Supabase retrieval with Groq generation plus metadata mapping and scoring
- **Auto-Update Engine**: Web scraping, document detection, and scheduled ingestion of new NAAC releases
- **Scheduler System**: APScheduler backed by a SQLite job store with endpoints for pause/resume/manage
- **Document Processing**: PDF/text chunking, cleaning, and single-row consolidation before vector upsert

### Frontend Components  
- **React TypeScript App (`apps/web`)**: Modern Material-UI interface
- **Chat Interface**: Natural language query processing with structured responses
- **System Dashboard**: Real-time monitoring of health, statistics, and operations
- **Document Upload**: PDF ingestion for NAAC and MVSR documents
- **Scheduler Manager**: Job management for automated updates

## 📋 Prerequisites

### System Requirements
- **Python 3.8+** (recommended 3.10+)
- **Node.js 16+** and npm/yarn
- **Git** for version control
- **4GB+ RAM** (8GB recommended)
- **2GB+ disk space** for documents and embeddings

### Required Services
- **Supabase**: PostgreSQL project with the `vector` extension enabled and a `chunks` table that matches `db_schema.txt`. Set `SUPABASE_DB_URL` and `SUPABASE_TABLE` to connect.
- **Groq API**: Provides the LLM endpoint (default `llama-3.3-70b-versatile`). Acquire a `GROQ_API_KEY` and keep it secret.

## 🚀 Quick Start Guide

### 1. Provision vector storage and LLM access

1. **Supabase vector store**
   - Create or reuse a Supabase project, enable the `vector` extension, and run the SQL in `db_schema.txt` to create `public.chunks`.
   - Copy the generated connection string (should include `postgresql://` and your credentials) and set it as `SUPABASE_DB_URL`.
   - Confirm `SUPABASE_TABLE` exists (default: `chunks`) and contains at least one row after a startup ingest.
2. **Groq API**
   - Sign up at Groq and create an API key.
   - Set `GROQ_API_KEY` in `.env` and ensure `GROQ_MODEL` points to your preferred model (default `llama-3.3-70b-versatile`).
3. **Verify connectivity**
   - Supabase: run a simple `psql` query or use the Supabase UI to SELECT from `public.chunks`.
   - Groq: `curl https://api.groq.com/openai/v1/chat/completions -H "Content-Type: application/json" -H "Authorization: Bearer $GROQ_API_KEY" -d "{\"model\":\"llama-3.3-70b-versatile\",\"messages\":[{\"role\":\"user\",\"content\":\"Reply exactly with OK.\"}],\"max_tokens\":5,\"temperature\":0}"`

### 2. Clone and Setup Backend

```bash
# Clone repository
git clone <your-repository-url>
cd EduBot

# Create Python virtual environment
python -m venv naac_env

# Activate virtual environment
# Windows:
naac_env\Scripts\activate
# macOS/Linux:
source naac_env/bin/activate

# Install Python dependencies
pip install -r requirements.txt
```

### 3. Setup Frontend

```bash
# Navigate to frontend directory
cd apps/web

# Install dependencies
npm install

# Return to project root
cd ..
```

### 4. Configuration

Create environment configuration file:

```bash
# Create .env file in project root
cp .env.example .env
```

Edit `.env` file with your settings:

```env
# Application
APP_NAME="NAAC Compliance Intelligence System"
DEBUG=false
HOST=0.0.0.0
PORT=8000
SERVERLESS_MODE=false
INGEST_INLINE_ON_SERVERLESS=true

# Vector Backend
VECTOR_BACKEND=supabase
SUPABASE_DB_URL=postgresql://user:password@db.supabase.co:5432/postgres
SUPABASE_TABLE=chunks
JOB_STORE_URL=sqlite:///jobs.sqlite

# Groq API
GROQ_MODEL=llama-3.3-70b-versatile
GROQ_API_KEY=
GROQ_TIMEOUT=120

# Embedding Configuration
EMBEDDING_MODEL=all-MiniLM-L6-v2
EMBEDDING_DEVICE=cpu

# Document Processing
CHUNK_SIZE=1000
CHUNK_OVERLAP=200

# NAAC Monitoring
NAAC_BASE_URL=https://www.naac.gov.in
CHECK_INTERVAL_HOURS=24
AUTO_INGEST_ENABLED=false
PERSIST_INGESTION_LOG=false
SERVERLESS_STATE_ENABLED=true
STAGED_UPLOAD_TTL_MINUTES=45
INGESTION_STATUS_TTL_HOURS=24

# Security (optional)
API_KEY=your-secure-api-key
AUTH_TOKEN_SECRET=replace-with-a-long-random-secret
AUTH_TOKEN_TTL_HOURS=8
CORS_ORIGINS=["http://localhost:3000"]

# Frontend (Vite) optional override
VITE_API_BASE_URL=
```

### 5. Start the System

#### Terminal 1 - Backend API
```bash
# Activate virtual environment if not already active
# Windows: naac_env\Scripts\activate
# macOS/Linux: source naac_env/bin/activate

# Start FastAPI server from repo root
python -m apps.backend.run_server

# Server will start at http://localhost:8000
```

#### Terminal 2 - Frontend Vite App
```bash
# Start Vite development server
npm --prefix apps/web run dev

# App will open at http://localhost:3000
```

Alternative (from repo root):

```bash
npm run dev:web
python -m apps.backend.run_server
```

## Vercel Deployment (Monorepo)

This repository is configured to deploy both frontend and backend on Vercel:

- Frontend static build output: `apps/web/build`
- Backend serverless entrypoint: `api/[...path].py`
- Routing/build settings: `vercel.json`

### Deploy Steps

1. Import this repository into Vercel.
2. Ensure project root is repository root.
3. Confirm build settings:
   - Build Command: `npm --prefix apps/web run build`
   - Output Directory: `apps/web/build`
4. Add required environment variables in Vercel Project Settings:
   - `SUPABASE_DB_URL`
   - `SUPABASE_TABLE`
   - `GROQ_API_KEY`
   - `GROQ_MODEL`
   - `SERVERLESS_MODE=true`
   - `INGEST_INLINE_ON_SERVERLESS=true`
   - `SERVERLESS_STATE_ENABLED=true`
   - `AUTH_TOKEN_SECRET` (required in production)
   - Any additional values from `.env` needed for your environment.
5. Deploy.

API requests from the frontend should continue to use `/api/...` paths.

Uploaded PDFs are staged in Postgres (via `SUPABASE_DB_URL`) so upload and ingest remain durable across stateless serverless invocations.

Vercel free plan note:
- Keep uploads reasonably small to avoid serverless execution limits during extraction/chunking.
- For very large PDFs, use a dedicated worker (Render/Railway/VM) and keep Vercel for frontend + query API.

### 6. Verify Installation

1. **Check Supabase**: Use the Supabase dashboard (or a `SELECT` query) to confirm `public.chunks` exists and contains at least one document after ingestion.
2. **Check Groq**: Run the Groq curl command above to ensure the key/model pair responds.
3. **Check Backend**: Visit `http://localhost:8000/health` (should show system health)
4. **Check Frontend**: Visit `http://localhost:3000` (should show chat interface)

## 📚 Initial Setup and Usage

### 1. Upload Initial Documents

#### NAAC Documents
Upload official NAAC documentation to establish requirements baseline:
- NAAC Manual for Universities
- Assessment and Accreditation Framework  
- Criterion-specific guidelines
- Assessment rubrics and scoring matrices

#### MVSR Evidence Documents
Upload institutional evidence supporting compliance:
- Institutional policies and procedures
- Academic reports and statistics
- Faculty and infrastructure documentation
- Student outcome assessments

### 2. System Configuration

#### Automatic Updates
The system automatically:
- Monitors NAAC website for new documents
- Downloads and processes updates
- Updates knowledge base incrementally 
- Maintains version history with rollback capability

#### Manual Scheduling (Optional)
Use the Scheduler Manager to configure:
- Daily update checks (recommended: 2:00 AM)
- Interval-based updates (every 6-12 hours)
- Criterion-specific updates for targeted monitoring

### 3. Query Examples

Try these sample queries to test the system:

```
"What are the NAAC requirements for Criterion 1.1?"
"Show me MVSR's evidence for academic diversity"  
"Analyze compliance gaps in curriculum design"
"Compare NAAC standards with MVSR practices"
"What documents are needed for accreditation?"
```

## 🔧 Advanced Configuration

### Custom Embedding Models
```python
# In apps/backend/config/settings.py
EMBEDDING_MODEL = "all-MiniLM-L6-v2"  # Default
# Alternatives:
# "sentence-transformers/all-mpnet-base-v2"  # Better accuracy, slower
# "sentence-transformers/all-distilroberta-v1"  # Balanced
```

### Performance Tuning
```env
# Increase for better retrieval accuracy
MAX_RETRIEVAL_RESULTS=15
SIMILARITY_THRESHOLD=0.65

# Adjust for document processing
CHUNK_SIZE=1200
CHUNK_OVERLAP=300

# GPU acceleration (if available)
EMBEDDING_DEVICE=cuda
```

### Production Deployment
```env
# Production settings
ENVIRONMENT=production
DEBUG=false
LOG_LEVEL=WARNING
CORS_ORIGINS=["https://your-domain.com"]

# Security
API_KEY=your-production-api-key
RATE_LIMIT_REQUESTS=50
RATE_LIMIT_WINDOW=3600
```

## 📊 System Monitoring

### Health Checks
- **System Health**: `/health` - Overall system status
- **Component Status**: Real-time monitoring of RAG pipeline, scheduler, database
- **Performance Metrics**: Response times, query counts, document statistics

### Logs and Debugging
```bash
# View API logs
tail -f apps/backend/logs/api.log

# View scheduler logs  
tail -f apps/backend/logs/scheduler.log

# View update operations
tail -f apps/backend/logs/updater.log
```

## 🛠️ Troubleshooting

### Common Issues

#### 1. Supabase connection failed
```bash
# Confirm SUPABASE_DB_URL is reachable
psql "$SUPABASE_DB_URL" -c "SELECT 1;"

# Ensure the vector extension/table exist (see db_schema.txt)
psql "$SUPABASE_DB_URL" -c "SELECT tablename FROM pg_tables WHERE tablename='chunks';"

# Check for vector index (vector extension must be installed)
psql "$SUPABASE_DB_URL" -c "SELECT indexname FROM pg_indexes WHERE tablename='chunks';"
```

#### 2. Groq API error
```bash
# Verify key + model combination
curl https://api.groq.com/openai/v1/chat/completions -H "Content-Type: application/json" -H "Authorization: Bearer $GROQ_API_KEY" -d "{\"model\":\"$GROQ_MODEL\",\"messages\":[{\"role\":\"user\",\"content\":\"Reply exactly with OK.\"}],\"max_tokens\":5,\"temperature\":0}"

# If you hit rate limits, try `GROQ_TIMEOUT=300` or upgrade your plan
```

#### 3. Package Installation Issues
```bash
# Update pip and setuptools
pip install --upgrade pip setuptools wheel

# Install packages one by one to identify issues
pip install fastapi uvicorn psycopg2-binary sentence-transformers groq

# For specific package conflicts:
pip install --no-deps <package-name>
```

#### 4. Memory Issues
```bash
# Reduce embedding model size
# Edit apps/backend/config/settings.py:
EMBEDDING_MODEL = "all-MiniLM-L6-v2"  # Smaller, faster

# Reduce chunk processing
CHUNK_SIZE = 800
MAX_RETRIEVAL_RESULTS = 5
```

### Port Conflicts
```bash
# Check what's using ports
netstat -ano | findstr :8000  # Windows
lsof -i :8000  # macOS/Linux

# Change ports in configuration
# Backend: PORT=8001 in .env
# Frontend: Change proxy in package.json
```

## 📈 Performance Optimization

### Database Optimization
- Monitor Supabase `chunks` table health, vacuum indexes, and keep `vector` extension statistics up to date
- Rebuild or reindex pgvector indexes when schema changes or retrieval latency spikes
- Trim older archived metadata or prune embeddings if storage grows above expectations

### Document Processing
- Batch processing for large document uploads  
- Parallel chunk processing for faster ingestion
- Smart duplicate detection to avoid reprocessing

### Query Optimization
- Query result caching for common requests
- Pre-computed embeddings for frequent queries
- Intelligent query routing based on complexity

## 🔒 Security Considerations

### API Security
```env
# Enable API key authentication
API_KEY=your-secure-random-key

# Rate limiting
RATE_LIMIT_REQUESTS=100
RATE_LIMIT_WINDOW=3600

# CORS configuration
CORS_ORIGINS=["https://your-domain.com"]
```

### Data Protection
- Document encryption at rest (optional)
- Secure file upload validation
- Access logging and audit trails
- Regular security updates

## 🤝 Contributing

### Development Setup
```bash
# Install development dependencies
pip install -r requirements-dev.txt
npm install --include=dev

# Run tests
python -m pytest tests/
npm test

# Code formatting
black apps/backend/
prettier --write apps/web/src/
```

### Code Style
- **Python**: Black formatter, PEP 8 compliance
- **TypeScript**: Prettier formatter, ESLint rules
- **Documentation**: Clear docstrings and type hints

## 📄 License

This project is licensed under the MIT License. See LICENSE file for details.

## 🆘 Support

### Getting Help
1. **Documentation**: Check this README and inline code documentation
2. **Issues**: Create GitHub issues for bugs or feature requests  
3. **Discussions**: Use GitHub Discussions for questions and ideas

### Contact Information
- **Project Maintainer**: [Your Name]
- **Email**: [your-email@domain.com]
- **Institution**: MVSR Engineering College

---

**Built with ❤️ for MVSR Engineering College NAAC Accreditation**

