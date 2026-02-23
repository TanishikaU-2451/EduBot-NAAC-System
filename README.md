# NAAC Compliance Intelligence System

A sophisticated **Retrieval-Augmented Generation (RAG) platform** designed to understand NAAC requirements, retrieve MVSR institutional evidence, and map MVSR practices to NAAC criteria with automatic updates and semantic reasoning.

## 🎯 System Overview

This is **NOT a generic chatbot** but a specialized compliance intelligence system that:

- **Understands NAAC Requirements**: Processes official NAAC documentation and assessment criteria
- **Retrieves MVSR Evidence**: Searches institutional documents and evidence supporting compliance
- **Maps Practices to Criteria**: Creates intelligent connections between MVSR practices and NAAC standards
- **Automatic Updates**: Monitors NAAC website for new guidelines and updates knowledge base automatically 
- **Semantic Intelligence**: Uses embedding-based retrieval and LLM reasoning (no hardcoded mappings)

## 🏗️ Architecture

### Backend Components
- **FastAPI REST API**: Exposes RAG pipeline through HTTP endpoints
- **ChromaDB Vector Store**: Separate collections for NAAC requirements and MVSR evidence
- **Ollama LLM Integration**: Local Llama3 model for response generation
- **RAG Pipeline**: Retrieval-Augmented Generation with metadata mapping
- **Auto-Update Engine**: Web scraping, document detection, and automatic ingestion
- **Scheduler System**: APScheduler with persistent job management
- **Document Processing**: PDF extraction with intelligent chunking

### Frontend Components  
- **React TypeScript App**: Modern Material-UI interface
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
- **Ollama**: Local LLM server with Llama3 model

## 🚀 Quick Start Guide

### 1. Install Ollama and Llama3

```bash
# Install Ollama (Windows)
# Download from: https://ollama.ai/download/windows
# Or use winget:
winget install Ollama.Ollama

# Install Ollama (macOS)
brew install ollama

# Install Ollama (Linux)
curl -fsSL https://ollama.ai/install.sh | sh

# Pull Llama3 model (this may take several minutes)
ollama pull llama3

# Verify Ollama is running (should start automatically)
ollama list
```

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
cd frontend

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
# Application Configuration
APP_NAME="NAAC Compliance Intelligence System"
DEBUG=false
HOST=0.0.0.0
PORT=8000

# Database Configuration
CHROMA_DB_PATH=./chroma_db
JOB_STORE_URL=sqlite:///jobs.sqlite

# Ollama Configuration
OLLAMA_HOST=http://localhost:11434
OLLAMA_MODEL=llama3
OLLAMA_TIMEOUT=120

# Document Processing
DATA_DIRECTORY=./data
CACHE_DIRECTORY=./cache
UPLOADS_DIRECTORY=./uploads
CHUNK_SIZE=1000
CHUNK_OVERLAP=200

# NAAC Monitoring
NAAC_BASE_URL=https://www.naac.gov.in
CHECK_INTERVAL_HOURS=24

# Security (optional)
API_KEY=your-secure-api-key
CORS_ORIGINS=["http://localhost:3000"]
```

### 5. Initialize Data Directories

```bash
# Create required directories
mkdir -p data/naac_documents data/mvsr_documents
mkdir -p cache uploads chroma_db
```

### 6. Start the System

#### Terminal 1 - Backend API
```bash
# Activate virtual environment if not already active
# Windows: naac_env\Scripts\activate
# macOS/Linux: source naac_env/bin/activate

# Start FastAPI server
cd backend
python -m api.main

# Server will start at http://localhost:8000
```

#### Terminal 2 - Frontend React App
```bash
# Start React development server
cd frontend
npm start

# App will open at http://localhost:3000
```

### 7. Verify Installation

1. **Check Ollama**: Visit `http://localhost:11434` (should show Ollama API)
2. **Check Backend**: Visit `http://localhost:8000/health` (should show system health)
3. **Check Frontend**: Visit `http://localhost:3000` (should show chat interface)

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
# In backend/config/settings.py
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
tail -f backend/logs/api.log

# View scheduler logs  
tail -f backend/logs/scheduler.log

# View update operations
tail -f backend/logs/updater.log
```

## 🛠️ Troubleshooting

### Common Issues

#### 1. Ollama Connection Failed
```bash
# Check if Ollama is running
curl http://localhost:11434/api/tags

# Restart Ollama service
# Windows: Restart from Services or Task Manager
# macOS/Linux: 
sudo systemctl restart ollama
# or
ollama serve
```

#### 2. ChromaDB Initialization Error
```bash
# Reset ChromaDB (will lose existing data)
rm -rf chroma_db/
mkdir chroma_db

# Restart backend to recreate database
```

#### 3. Package Installation Issues
```bash
# Update pip and setuptools
pip install --upgrade pip setuptools wheel

# Install packages one by one to identify issues
pip install fastapi uvicorn chromadb sentence-transformers

# For specific package conflicts:
pip install --no-deps <package-name>
```

#### 4. Memory Issues
```bash
# Reduce embedding model size
# Edit backend/config/settings.py:
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
- Regular ChromaDB cleanup and optimization
- Index rebuilding for better query performance
- Vector dimension reduction for faster similarity search

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
black backend/
prettier --write frontend/src/
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