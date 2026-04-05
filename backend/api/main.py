"""
FastAPI Main Application for NAAC Compliance Intelligence System
Provides REST API endpoints for the complete RAG pipeline and auto-update system
"""

from fastapi import FastAPI, HTTPException, BackgroundTasks, Depends, UploadFile, File, Form, APIRouter
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from typing import Any, Dict, List, Optional
import logging
import asyncio
from datetime import datetime
from pathlib import Path
import os
from contextlib import asynccontextmanager
from threading import Lock
from uuid import uuid4

# Import our system components
from ..rag.pipeline import RAGPipeline
from ..rag.metadata_mapper import NAACMetadataMapper
try:
    from ..db.supabase_store import SupabaseVectorStore  # type: ignore[attr-defined]
    SUPABASE_IMPORT_ERROR = None
except Exception as import_exc:  # pragma: no cover - optional dependency
    SupabaseVectorStore = None  # type: ignore[assignment]
    SUPABASE_IMPORT_ERROR = import_exc

from ..db.local_store import LocalVectorStore
from ..llm.groq_client import GroqClient
from ..memory.memory_store import ConversationMemoryStore, MemoryIdentity
from ..ingestion.ingest import DocumentIngestionPipeline
from ..updater.auto_ingest import NAACAutoIngest
from ..scheduler.update_scheduler import NAACUpdateScheduler
from ..config.settings import get_settings
from ..auth.auth import authenticate, validate_token, logout, get_session_info


# Get application settings
settings = get_settings()

# Configure logging from settings for easier DB diagnostics
logging.basicConfig(
    level=getattr(logging, settings.log_level.upper(), logging.INFO),
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)
logger = logging.getLogger(__name__)

# Global system components (initialized on startup)
rag_pipeline: Optional[RAGPipeline] = None
auto_ingest: Optional[NAACAutoIngest] = None
scheduler: Optional[NAACUpdateScheduler] = None
metadata_mapper: Optional[NAACMetadataMapper] = None
vector_store_instance: Optional[Any] = None
memory_store_instance: Optional[ConversationMemoryStore] = None
ingestion_pipeline_instance: Optional[DocumentIngestionPipeline] = None
ingestion_status_store: Dict[str, Dict[str, Any]] = {}
ingestion_status_lock = Lock()
ACTIVE_INGEST_STATUSES = {"queued", "processing"}
staged_upload_store: Dict[str, Dict[str, Any]] = {}
staged_upload_lock = Lock()
STAGED_UPLOAD_PREFIX = "memory://upload/"
PROJECT_ROOT = Path(__file__).resolve().parents[2]

# Pydantic models for request/response
class QueryRequest(BaseModel):
    query: str = Field(..., description="Natural language query about NAAC compliance")
    filters: Optional[Dict[str, Any]] = Field(None, description="Optional filters for retrieval")
    include_sources: bool = Field(True, description="Include source details in response")
    tenant_id: Optional[str] = Field(None, description="Tenant scope for memory")
    user_id: Optional[str] = Field(None, description="User scope for memory")
    conversation_id: Optional[str] = Field(None, description="Conversation scope for memory")

class ComplianceResponse(BaseModel):
    naac_requirement: str = Field(..., description="Relevant NAAC requirements")
    mvsr_evidence: str = Field(..., description="MVSR supporting evidence")
    naac_mapping: str = Field(..., description="NAAC criterion mapping")
    compliance_analysis: str = Field(..., description="Detailed compliance analysis")
    status: str = Field(..., description="Compliance status")
    recommendations: str = Field(..., description="Gap resolution recommendations")
    confidence_score: float = Field(..., description="Response confidence score")
    compliance_score: Optional[Dict[str, Any]] = Field(None, description="Numerical compliance scoring")
    detailed_sources: Optional[Dict[str, Any]] = Field(None, description="Detailed source information")

class IngestRequest(BaseModel):
    document_type: str = Field(..., description="Document type: 'naac_requirement' or 'mvsr_evidence'")
    file_paths: List[str] = Field(..., description="List of staged upload identifiers to ingest")
    force_reingest: bool = Field(False, description="Force reingest of existing documents")
    additional_metadata: Optional[Dict[str, Any]] = Field(None, description="Additional metadata")

class IngestStatusRequest(BaseModel):
    file_paths: List[str] = Field(..., description="List of staged upload identifiers to inspect")

class UpdateRequest(BaseModel):
    update_type: str = Field("incremental", description="Update type: 'incremental', 'full', 'criterion'")
    criteria: Optional[List[str]] = Field(None, description="Specific criteria for criterion updates")
    force_check: bool = Field(False, description="Force check even if recently updated")

class ScheduleRequest(BaseModel):
    job_type: str = Field(..., description="Job type: 'daily', 'interval', 'criterion'")
    schedule: str = Field(..., description="Cron expression or interval specification")
    criteria: Optional[List[str]] = Field(None, description="Criteria for criterion-specific jobs")
    enabled: bool = Field(True, description="Whether job should be enabled")


class UploadResponse(BaseModel):
    status: str = Field(..., description="Upload status")
    message: str = Field(..., description="Upload result message")
    filename: str = Field(..., description="Original uploaded filename")
    stored_filename: str = Field(..., description="Display filename retained for the staged upload")
    stored_path: str = Field(..., description="Server-side staged upload identifier for later ingestion")
    document_type: str = Field(..., description="Document type associated with the file")
    file_size: int = Field(..., description="Uploaded file size in bytes")
    timestamp: str = Field(..., description="Upload completion timestamp")


class StagedUploadDeleteRequest(BaseModel):
    stored_path: str = Field(..., description="Server-side staged upload identifier to remove")

class LoginRequest(BaseModel):
    username: str = Field(..., description="Username")
    password: str = Field(..., description="Password")

class LoginResponse(BaseModel):
    token: str = Field(..., description="Session token")
    username: str = Field(..., description="Authenticated username")
    expires_at: str = Field(..., description="Token expiry (UTC ISO)")
    message: str = Field(..., description="Login status message")



# Lifespan management
@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan management"""
    # Startup
    logger.info("Starting NAAC Compliance Intelligence System")
    
    try:
        await initialize_system()
        logger.info("System initialized successfully")
        yield
    except Exception as e:
        logger.error(f"Failed to initialize system: {e}")
        raise
    finally:
        # Shutdown
        logger.info("Shutting down NAAC Compliance Intelligence System")
        await shutdown_system()

# Initialize FastAPI app
app = FastAPI(
    title=settings.app_name,
    description="A Retrieval-Augmented Generation platform for NAAC compliance analysis",
    version=settings.app_version,
    lifespan=lifespan
)

# Create API router with /api prefix
api_router = APIRouter(prefix="/api")

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=settings.cors_allow_credentials,
    allow_methods=["*"],
    allow_headers=["*"],
)

async def initialize_system():
    """Initialize all system components"""
    global rag_pipeline, auto_ingest, scheduler, metadata_mapper, vector_store_instance, memory_store_instance, ingestion_pipeline_instance
    
    try:
        # Initialize configured vector store with local fallback
        vector_backend = (settings.vector_backend or "supabase").lower()
        use_supabase = vector_backend == "supabase"

        if use_supabase and not settings.supabase_db_url:
            logger.warning("SUPABASE_DB_URL missing; falling back to local vector store")
            use_supabase = False

        if use_supabase and SupabaseVectorStore is None:
            logger.warning(
                "Supabase backend requested but dependencies are unavailable: %s. "
                "Falling back to local vector store.",
                SUPABASE_IMPORT_ERROR,
            )
            use_supabase = False

        if use_supabase and SupabaseVectorStore is not None:
            logger.info("Initializing Supabase vector backend")
            vector_store = SupabaseVectorStore(
                db_url=settings.supabase_db_url,
                table_name=settings.supabase_table,
                embedding_model=settings.embedding_model,
                embedding_dim=settings.embedding_dim,
                embedding_device=settings.embedding_device,
                embedding_batch_size=settings.embedding_batch_size,
                insert_batch_size=settings.vector_insert_batch_size,
            )
            consolidate = getattr(vector_store, "consolidate_single_row_mode", None)
            if callable(consolidate):
                consolidate()
        else:
            logger.info("Initializing in-memory vector backend for local usage")
            vector_store = LocalVectorStore(
                embedding_model=settings.embedding_model,
                embedding_device=settings.embedding_device,
                embedding_batch_size=settings.embedding_batch_size,
            )
        vector_store_instance = vector_store

        if settings.memory_enabled and settings.supabase_db_url:
            memory_store = ConversationMemoryStore(
                db_url=settings.supabase_db_url,
                embedding_model=settings.embedding_model,
                embedding_dim=settings.embedding_dim,
                embedding_device=settings.embedding_device,
                short_ttl_days=settings.memory_short_ttl_days,
                long_ttl_days=settings.memory_long_ttl_days,
                short_limit=settings.memory_short_limit,
                long_top_k=settings.memory_long_top_k,
            )
            memory_store.initialize_schema()
            memory_store.clear_short_term_memory()
            memory_store_instance = memory_store
        else:
            memory_store_instance = None
        
        # Initialize Groq client
        llm_client = GroqClient(
            model_name=settings.groq_model,
            api_key=settings.groq_api_key,
            timeout=settings.groq_timeout,
            allow_missing_api_key=True,
        )
        
        # Initialize ingestion pipeline
        ingestion_pipeline = DocumentIngestionPipeline(
            vector_store=vector_store,
            chunk_size=settings.chunk_size,
            chunk_overlap=settings.chunk_overlap,
            large_document_page_threshold=settings.large_document_page_threshold,
            large_document_chunk_size=settings.large_document_chunk_size,
            large_document_chunk_overlap=settings.large_document_chunk_overlap,
            min_chunk_length=settings.min_chunk_length,
            pdf_extraction_strategy=settings.pdf_extraction_strategy,
            pdf_extract_tables=settings.pdf_extract_tables,
            persist_ingestion_log=settings.persist_ingestion_log,
        )
        ingestion_pipeline_instance = ingestion_pipeline
        
        # Initialize RAG pipeline
        rag_pipeline = RAGPipeline(
            chroma_store=vector_store,
            llm_client=llm_client,
            retrieval_config={
                "default_k_naac": settings.max_retrieval_results,
                "default_k_mvsr": settings.max_retrieval_results,
                "similarity_threshold": settings.similarity_threshold,
                "retrieval_mode": settings.retrieval_mode,
                "dense_weight": settings.retrieval_dense_weight,
                "lexical_weight": settings.retrieval_lexical_weight,
                "candidate_multiplier": settings.retrieval_candidate_multiplier,
                # Cross-encoder reranker
                "reranker_enabled": settings.reranker_enabled,
                "reranker_model": settings.reranker_model,
                "reranker_device": settings.reranker_device,
            },
        )
        
        if settings.auto_ingest_enabled:
            auto_ingest = NAACAutoIngest(
                chroma_store=vector_store,
                ingestion_pipeline=ingestion_pipeline,
            )
            scheduler = NAACUpdateScheduler(auto_ingest=auto_ingest)
            scheduler.start()
        else:
            auto_ingest = None
            scheduler = None
            logger.info("Auto-ingest and scheduler are disabled; no local data/cache directories will be created.")

        # Initialize metadata mapper
        metadata_mapper = NAACMetadataMapper()
        
        logger.info("All system components initialized")
        
    except Exception as e:
        logger.error(f"System initialization failed: {e}")
        raise

async def shutdown_system():
    """Shutdown system components"""
    global scheduler
    
    if scheduler:
        scheduler.stop()

# Dependency functions
def get_rag_pipeline() -> RAGPipeline:
    """Dependency to get RAG pipeline"""
    if rag_pipeline is None:
        raise HTTPException(status_code=503, detail="RAG pipeline not initialized")
    return rag_pipeline

def get_auto_ingest() -> NAACAutoIngest:
    """Dependency to get auto-ingest system"""
    if auto_ingest is None:
        raise HTTPException(status_code=503, detail="Auto-ingest system not initialized")
    return auto_ingest

def get_scheduler() -> NAACUpdateScheduler:
    """Dependency to get scheduler"""
    if scheduler is None:
        raise HTTPException(status_code=503, detail="Scheduler not initialized")
    return scheduler

def get_metadata_mapper() -> NAACMetadataMapper:
    """Dependency to get metadata mapper"""
    if metadata_mapper is None:
        raise HTTPException(status_code=503, detail="Metadata mapper not initialized")
    return metadata_mapper


def get_vector_store() -> Any:
    """Dependency to get vector store"""
    if vector_store_instance is None:
        raise HTTPException(status_code=503, detail="Vector store not initialized")
    return vector_store_instance


def get_memory_store() -> Optional[ConversationMemoryStore]:
    """Dependency to get memory store (optional)."""
    return memory_store_instance


def get_ingestion_pipeline() -> DocumentIngestionPipeline:
    """Dependency to get the document ingestion pipeline."""
    if ingestion_pipeline_instance is None:
        raise HTTPException(status_code=503, detail="Document ingestion pipeline not initialized")
    return ingestion_pipeline_instance


def _build_memory_identity(request: QueryRequest) -> MemoryIdentity:
    return MemoryIdentity(
        tenant_id=(request.tenant_id or "default_tenant").strip() or "default_tenant",
        user_id=(request.user_id or "default_user").strip() or "default_user",
        conversation_id=(request.conversation_id or "default_conversation").strip() or "default_conversation",
    )


def _build_assistant_memory_text(response: Dict[str, Any]) -> str:
    parts = []
    if response.get("compliance_analysis"):
        parts.append(str(response["compliance_analysis"]).strip())
    if response.get("recommendations"):
        parts.append(f"Recommendations: {str(response['recommendations']).strip()}")
    if response.get("status"):
        parts.append(f"Status: {str(response['status']).strip()}")
    return "\n\n".join([p for p in parts if p])


def _is_staged_upload_token(file_path: str) -> bool:
    return str(file_path or "").strip().startswith(STAGED_UPLOAD_PREFIX)


def _create_staged_upload_token(filename: str) -> str:
    safe_name = Path(filename or "uploaded.pdf").name
    return f"{STAGED_UPLOAD_PREFIX}{uuid4().hex}/{safe_name}"


def _set_staged_upload(
    token: str,
    *,
    content: bytes,
    filename: str,
    document_type: str,
) -> Dict[str, Any]:
    record = {
        "token": token,
        "content": content,
        "filename": Path(filename or "uploaded.pdf").name,
        "document_type": document_type,
        "file_size": len(content or b""),
        "created_at": datetime.now().isoformat(),
    }
    with staged_upload_lock:
        staged_upload_store[token] = record
    return record.copy()


def _get_staged_upload(token: str) -> Optional[Dict[str, Any]]:
    with staged_upload_lock:
        record = staged_upload_store.get(token)
        return record.copy() if record else None


def _remove_staged_upload(token: str) -> Optional[Dict[str, Any]]:
    with staged_upload_lock:
        record = staged_upload_store.pop(token, None)
        return record.copy() if record else None


def _normalize_ingestion_path(file_path: str) -> str:
    normalized = str(file_path or "").strip()
    if _is_staged_upload_token(normalized):
        return normalized
    candidate = Path(normalized)
    if not candidate.is_absolute():
        candidate = (PROJECT_ROOT / normalized).resolve()
    else:
        candidate = candidate.resolve()
    return str(candidate)


def _set_ingestion_status(
    file_path: str,
    status: str,
    *,
    phase: Optional[str] = None,
    message: Optional[str] = None,
    **extra: Any,
) -> Dict[str, Any]:
    normalized_path = _normalize_ingestion_path(file_path)
    now = datetime.now().isoformat()

    with ingestion_status_lock:
        current = ingestion_status_store.get(normalized_path, {}).copy()
        updated = {
            **current,
            **extra,
            "file_path": normalized_path,
            "status": status,
            "updated_at": now,
        }
        if phase is not None:
            updated["phase"] = phase
        if message is not None:
            updated["message"] = message
        if status in ACTIVE_INGEST_STATUSES and not updated.get("started_at"):
            updated["started_at"] = now
        if status in {"completed", "failed"}:
            updated["completed_at"] = now
        ingestion_status_store[normalized_path] = updated
        return updated.copy()


def _remove_ingestion_status(file_path: str) -> None:
    normalized_path = _normalize_ingestion_path(file_path)
    with ingestion_status_lock:
        ingestion_status_store.pop(normalized_path, None)


def _get_ingestion_statuses(file_paths: List[str]) -> Dict[str, Dict[str, Any]]:
    normalized_paths = [_normalize_ingestion_path(path) for path in file_paths]
    with ingestion_status_lock:
        return {
            path: ingestion_status_store.get(
                path,
                {
                    "file_path": path,
                    "status": "unknown",
                    "phase": "unknown",
                    "message": "No ingestion status available yet.",
                },
            ).copy()
            for path in normalized_paths
        }


def _has_active_manual_ingestion() -> bool:
    with ingestion_status_lock:
        return any(
            status_row.get("status") in ACTIVE_INGEST_STATUSES
            for status_row in ingestion_status_store.values()
        )

# API Endpoints

@api_router.post("/auth/login", response_model=LoginResponse)
async def login_endpoint(request: LoginRequest):
    """Authenticate and return a session token"""
    token = authenticate(request.username, request.password)
    if not token:
        raise HTTPException(status_code=401, detail="Invalid username or password")
    
    session = get_session_info(token)
    return LoginResponse(
        token=token,
        username=request.username,
        expires_at=session["expires_at"] if session else "",
        message="Login successful"
    )

@api_router.get("/health")
async def health_check():
    """System health check"""
    try:
        health_status = {
            "timestamp": datetime.now().isoformat(),
            "status": "healthy",
            "components": {
                "rag_pipeline": rag_pipeline is not None,
                "auto_ingest": auto_ingest is not None,
                "scheduler": scheduler is not None and scheduler.scheduler.running if scheduler else False,
                "metadata_mapper": metadata_mapper is not None,
                "memory_layer": memory_store_instance is not None,
            }
        }
        
        # Check RAG pipeline health if available
        if rag_pipeline:
            pipeline_health = rag_pipeline.get_pipeline_health()
            health_status["pipeline_health"] = pipeline_health
            
            if pipeline_health.get("overall_status") != "healthy":
                health_status["status"] = "degraded"

        if memory_store_instance:
            memory_health = memory_store_instance.get_health()
            health_status["memory_health"] = memory_health
            if not memory_health.get("ok", False):
                health_status["status"] = "degraded"
        
        return health_status
        
    except Exception as e:
        logger.error(f"Health check failed: {e}")
        return JSONResponse(
            status_code=503,
            content={
                "timestamp": datetime.now().isoformat(),
                "status": "unhealthy",
                "error": str(e)
            }
        )

@api_router.post("/query", response_model=ComplianceResponse)
async def query_compliance(
    request: QueryRequest,
    pipeline: RAGPipeline = Depends(get_rag_pipeline),
    memory_store: Optional[ConversationMemoryStore] = Depends(get_memory_store),
):
    """
    Query the NAAC compliance system
    
    Process natural language queries and return structured compliance analysis
    """
    try:
        if _has_active_manual_ingestion():
            raise HTTPException(
                status_code=409,
                detail="Chunking in progress. Wait until both documents finish processing.",
            )

        logger.info(f"Processing query: {request.query[:100]}...")
        
        memory_context: Optional[Dict[str, Any]] = None
        memory_identity: Optional[MemoryIdentity] = None
        if memory_store:
            try:
                memory_store.cleanup_expired()
                memory_identity = _build_memory_identity(request)
                memory_context = memory_store.get_context(memory_identity, request.query)
            except Exception as memory_err:
                logger.warning(f"Memory fetch failed; continuing without memory context: {memory_err}")
                memory_context = None

        # Process query through RAG pipeline (run sync function in thread to avoid blocking)
        import asyncio
        response = await asyncio.to_thread(
            pipeline.process_query,
            request.query,
            request.filters,
            memory_context,
        )

        if memory_store and memory_identity:
            try:
                assistant_text = _build_assistant_memory_text(response)
                memory_store.add_messages(
                    memory_identity,
                    [
                        {
                            "role": "user",
                            "content": request.query,
                            "metadata": {"source": "query_endpoint"},
                        },
                        {
                            "role": "assistant",
                            "content": assistant_text,
                            "metadata": {
                                "status": response.get("status", "Unknown"),
                                "source": "query_endpoint",
                            },
                        },
                    ],
                )
            except Exception as memory_write_err:
                logger.warning(f"Memory write failed; response already generated: {memory_write_err}")
        
        # Format response
        compliance_response = ComplianceResponse(
            naac_requirement=response.get("naac_requirement", ""),
            mvsr_evidence=response.get("mvsr_evidence", ""),
            naac_mapping=response.get("naac_mapping", ""),
            compliance_analysis=response.get("compliance_analysis", ""),
            status=response.get("status", "Unknown"),
            recommendations=response.get("recommendations", ""),
            confidence_score=response.get("confidence_score", 0.0),
            compliance_score=response.get("compliance_score"),
            detailed_sources=response.get("detailed_sources") if request.include_sources else None
        )
        
        return compliance_response
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Query processing failed: {e}")
        raise HTTPException(status_code=500, detail=f"Query processing failed: {str(e)}")

@api_router.post("/ingest")
async def ingest_documents(
    request: IngestRequest,
    background_tasks: BackgroundTasks,
    ingestion_pipeline: DocumentIngestionPipeline = Depends(get_ingestion_pipeline),
):
    """
    Ingest documents into the knowledge base
    
    Process PDF documents and add them to the vector store
    """
    try:
        def run_ingestion():
            """Background task for document ingestion"""
            try:
                results = []
                for raw_path in request.file_paths:
                    file_path = _normalize_ingestion_path(raw_path)

                    if _is_staged_upload_token(file_path):
                        staged_upload = _get_staged_upload(file_path)
                        if not staged_upload:
                            logger.warning(f"Ingest: staged upload not found for token {file_path}")
                            _set_ingestion_status(
                                file_path,
                                "failed",
                                phase="missing_upload",
                                message="The staged upload is no longer available. Please upload the PDF again.",
                            )
                            results.append({
                                "file": file_path,
                                "status": "failed",
                                "error": "Staged upload not found",
                            })
                            continue
                        file_name = str(staged_upload.get("filename") or "uploaded.pdf")
                    else:
                        resolved = Path(file_path)
                        if not resolved.exists():
                            logger.warning(f"Ingest: file not found at {file_path}")
                            _set_ingestion_status(
                                file_path,
                                "failed",
                                phase="missing_file",
                                message=f"File not found: {file_path}",
                            )
                            results.append({
                                "file": file_path,
                                "status": "failed",
                                "error": f"File not found: {file_path}"
                            })
                            continue
                        file_name = resolved.name

                    logger.info(f"Ingest: processing {file_name} as {request.document_type}")
                    _set_ingestion_status(
                        file_path,
                        "processing",
                        phase="starting",
                        message="Starting document extraction and chunking...",
                        document_type=request.document_type,
                        filename=file_name,
                    )

                    def status_callback(update: Dict[str, Any], tracked_path: str = file_path):
                        if not isinstance(update, dict):
                            return
                        next_status = str(update.get("status") or "processing")
                        next_phase = update.get("phase")
                        next_message = update.get("message")
                        extra = {
                            key: value
                            for key, value in update.items()
                            if key not in {"status", "phase", "message"}
                        }
                        _set_ingestion_status(
                            tracked_path,
                            next_status,
                            phase=str(next_phase) if next_phase is not None else None,
                            message=str(next_message) if next_message is not None else None,
                            **extra,
                        )

                    try:
                        if _is_staged_upload_token(file_path):
                            result = ingestion_pipeline.ingest_staged_document(
                                file_bytes=staged_upload["content"],
                                file_name=file_name,
                                staged_identifier=file_path,
                                document_type=request.document_type,
                                additional_metadata=request.additional_metadata,
                                status_callback=status_callback,
                            )
                        else:
                            result = ingestion_pipeline.ingest_single_document(
                                file_path=file_path,
                                document_type=request.document_type,
                                additional_metadata=request.additional_metadata,
                                status_callback=status_callback,
                            )
                    finally:
                        if _is_staged_upload_token(file_path):
                            _remove_staged_upload(file_path)

                    if result.get("status") == "success":
                        _set_ingestion_status(
                            file_path,
                            "completed",
                            phase="completed",
                            message=f"Processed into {result.get('chunks_written', 0)} chunks and stored successfully.",
                            document_type=request.document_type,
                            chunks_generated=result.get("chunks_generated", 0),
                            chunks_written=result.get("chunks_written", 0),
                            debug_trace_id=result.get("debug_trace_id"),
                        )
                    else:
                        _set_ingestion_status(
                            file_path,
                            "failed",
                            phase="failed",
                            message=str(result.get("error", "Document ingestion failed.")),
                            document_type=request.document_type,
                            debug_trace_id=result.get("debug_trace_id"),
                        )
                    results.append(result)
                
                logger.info(f"Ingestion completed: {len(results)} documents processed")
                
            except Exception as e:
                logger.error(f"Background ingestion failed: {e}")
        
        resolved_paths = []
        for raw_path in request.file_paths:
            resolved_path = _normalize_ingestion_path(raw_path)
            resolved_paths.append(resolved_path)
            _set_ingestion_status(
                resolved_path,
                "queued",
                phase="queued",
                message="Queued for chunking and embedding.",
                document_type=request.document_type,
            )

        # Start background ingestion
        background_tasks.add_task(run_ingestion)
        
        return {
            "status": "accepted",
            "message": f"Ingestion started for {len(request.file_paths)} documents",
            "document_type": request.document_type,
            "file_paths": resolved_paths,
            "timestamp": datetime.now().isoformat()
        }
        
    except Exception as e:
        logger.error(f"Ingestion request failed: {e}")
        raise HTTPException(status_code=500, detail=f"Ingestion failed: {str(e)}")


@api_router.post("/ingest/status")
async def get_ingest_status(request: IngestStatusRequest):
    """Return current ingestion state for staged file paths."""
    try:
        return {
            "statuses": _get_ingestion_statuses(request.file_paths),
            "timestamp": datetime.now().isoformat(),
        }
    except Exception as e:
        logger.error(f"Ingestion status request failed: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to fetch ingestion status: {str(e)}")

@api_router.post("/force-update")
async def force_system_update(
    request: UpdateRequest,
    background_tasks: BackgroundTasks,
    auto_ingest_system: NAACAutoIngest = Depends(get_auto_ingest)
):
    """
    Force an immediate system update
    
    Trigger document checking and knowledge base updates
    """
    try:
        def run_update():
            """Background task for system update"""
            try:
                if request.update_type == "full":
                    report = auto_ingest_system.force_full_update()
                elif request.update_type == "criterion" and request.criteria:
                    report = auto_ingest_system.run_criterion_specific_update(request.criteria)
                else:
                    report = auto_ingest_system.run_incremental_update()
                
                logger.info(f"Update completed: {report.operation_id}")
                
            except Exception as e:
                logger.error(f"Background update failed: {e}")
        
        # Start background update
        background_tasks.add_task(run_update)
        
        return {
            "status": "accepted",
            "message": f"System update started ({request.update_type})",
            "update_type": request.update_type,
            "criteria": request.criteria,
            "timestamp": datetime.now().isoformat()
        }
        
    except Exception as e:
        logger.error(f"Update request failed: {e}")
        raise HTTPException(status_code=500, detail=f"Update failed: {str(e)}")

@api_router.get("/last-sync")
async def get_last_sync():
    """
    Get information about the last synchronization
    
    Returns details about the most recent update operation
    """
    try:
        if auto_ingest is None:
            return {
                "last_successful_update": None,
                "recent_operations": [],
                "system_status": "disabled",
                "component_statistics": {},
                "timestamp": datetime.now().isoformat()
            }

        status = auto_ingest.get_update_status()
        
        return {
            "last_successful_update": status.get("last_successful_update"),
            "recent_operations": status.get("recent_operations", [])[-5:],  # Last 5 operations
            "system_status": status.get("system_status"),
            "component_statistics": status.get("component_statistics"),
            "timestamp": datetime.now().isoformat()
        }
        
    except Exception as e:
        logger.error(f"Last sync request failed: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get sync status: {str(e)}")

@api_router.get("/scheduler/status")
async def get_scheduler_status():
    """Get scheduler status and job information"""
    try:
        if scheduler is None:
            return {
                "scheduler_status": {
                    "running": False,
                    "job_count": 0,
                    "next_run_time": None,
                    "uptime_hours": 0.0,
                },
                "jobs": [],
                "timestamp": datetime.now().isoformat(),
            }

        status = scheduler.get_scheduler_status()
        jobs = scheduler.get_job_list()

        # Calculate uptime hours
        uptime_hours = 0.0
        if scheduler.start_time and status.is_running:
            uptime_delta = datetime.now() - scheduler.start_time
            uptime_hours = uptime_delta.total_seconds() / 3600

        # Transform jobs to match frontend expectations
        transformed_jobs = []
        for job in jobs:
            # Determine status based on job state
            if not job.enabled:
                job_status = 'paused'
            elif job.last_result == 'failed':
                job_status = 'failed'
            elif job.next_run:
                job_status = 'scheduled'
            else:
                job_status = 'paused'

            transformed_jobs.append({
                'id': job.job_id,
                'name': job.description,
                'job_type': job.job_type,
                'schedule': job.schedule,
                'next_run_time': job.next_run,
                'status': job_status,
                'created_at': datetime.now().isoformat(),  # Placeholder
                'last_run': job.last_run,
                'run_count': 0  # Placeholder - not tracked currently
            })

        # Transform to match frontend expectations
        return {
            "scheduler_status": {
                "running": status.is_running,
                "job_count": status.total_jobs,
                "next_run_time": status.next_scheduled_update,
                "uptime_hours": round(uptime_hours, 2)
            },
            "jobs": transformed_jobs,
            "timestamp": datetime.now().isoformat()
        }

    except Exception as e:
        logger.error(f"Scheduler status request failed: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get scheduler status: {str(e)}")

@api_router.post("/scheduler/schedule")
async def schedule_job(
    request: ScheduleRequest,
    scheduler_system: NAACUpdateScheduler = Depends(get_scheduler)
):
    """Schedule a new automated job"""
    try:
        success = False
        
        if request.job_type == "daily":
            # Parse hour and minute from schedule string (e.g., "02:30")
            try:
                hour, minute = map(int, request.schedule.split(":"))
                success = scheduler_system.schedule_daily_update(hour=hour, minute=minute)
            except ValueError:
                raise HTTPException(status_code=400, detail="Daily schedule must be in HH:MM format")
        
        elif request.job_type == "interval":
            # Parse interval hours from schedule string (e.g., "6")
            try:
                hours = int(request.schedule)
                success = scheduler_system.schedule_interval_update(hours=hours)
            except ValueError:
                raise HTTPException(status_code=400, detail="Interval schedule must be number of hours")
        
        elif request.job_type == "criterion":
            if not request.criteria:
                raise HTTPException(status_code=400, detail="Criteria required for criterion-specific jobs")
            success = scheduler_system.schedule_criterion_specific_update(
                criteria=request.criteria,
                cron_expression=request.schedule
            )
        
        else:
            raise HTTPException(status_code=400, detail="Invalid job type")
        
        if success:
            return {
                "status": "success",
                "message": f"Job scheduled successfully",
                "job_type": request.job_type,
                "schedule": request.schedule,
                "timestamp": datetime.now().isoformat()
            }
        else:
            raise HTTPException(status_code=500, detail="Failed to schedule job")
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Job scheduling failed: {e}")
        raise HTTPException(status_code=500, detail=f"Scheduling failed: {str(e)}")

@api_router.post("/scheduler/jobs/{job_id}/pause")
async def pause_job(job_id: str, scheduler_system: NAACUpdateScheduler = Depends(get_scheduler)):
    """Pause a scheduled job"""
    try:
        success = scheduler_system.pause_job(job_id)
        
        if success:
            return {"status": "success", "message": f"Job {job_id} paused"}
        else:
            raise HTTPException(status_code=404, detail="Job not found or could not be paused")
        
    except Exception as e:
        logger.error(f"Job pause failed: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to pause job: {str(e)}")

@api_router.post("/scheduler/jobs/{job_id}/resume")
async def resume_job(job_id: str, scheduler_system: NAACUpdateScheduler = Depends(get_scheduler)):
    """Resume a paused job"""
    try:
        success = scheduler_system.resume_job(job_id)
        
        if success:
            return {"status": "success", "message": f"Job {job_id} resumed"}
        else:
            raise HTTPException(status_code=404, detail="Job not found or could not be resumed")
        
    except Exception as e:
        logger.error(f"Job resume failed: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to resume job: {str(e)}")

@api_router.delete("/scheduler/jobs/{job_id}")
async def remove_job(job_id: str, scheduler_system: NAACUpdateScheduler = Depends(get_scheduler)):
    """Remove a scheduled job"""
    try:
        success = scheduler_system.remove_job(job_id)
        
        if success:
            return {"status": "success", "message": f"Job {job_id} removed"}
        else:
            raise HTTPException(status_code=404, detail="Job not found or could not be removed")
        
    except Exception as e:
        logger.error(f"Job removal failed: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to remove job: {str(e)}")

@api_router.get("/mapping/analyze")
async def analyze_query_mapping(
    query: str,
    mapper: NAACMetadataMapper = Depends(get_metadata_mapper)
):
    """
    Analyze query mapping to NAAC criteria and MVSR categories
    
    Helps understand how queries are interpreted by the system
    """
    try:
        mapping_analysis = mapper.get_comprehensive_mapping(query)
        
        return {
            "query": query,
            "analysis": mapping_analysis,
            "timestamp": datetime.now().isoformat()
        }
        
    except Exception as e:
        logger.error(f"Mapping analysis failed: {e}")
        raise HTTPException(status_code=500, detail=f"Mapping analysis failed: {str(e)}")

@api_router.get("/stats")
async def get_system_statistics(
    pipeline: RAGPipeline = Depends(get_rag_pipeline),
):
    """Get comprehensive system statistics"""
    try:
        pipeline_stats = pipeline.get_pipeline_stats()
        update_status = (
            auto_ingest.get_update_status()
            if auto_ingest is not None
            else {
                "system_status": "disabled",
                "message": "Auto-ingest is disabled.",
                "recent_operations": [],
            }
        )
        
        return {
            "pipeline_statistics": pipeline_stats,
            "update_status": update_status,
            "timestamp": datetime.now().isoformat()
        }
        
    except Exception as e:
        logger.error(f"Statistics request failed: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get statistics: {str(e)}")


@api_router.get("/db/health")
async def get_db_health(vector_store: Any = Depends(get_vector_store)):
    """Database health and connectivity diagnostics for Supabase."""
    try:
        health = vector_store.health_check()
        if not health.get("ok", False):
            return JSONResponse(status_code=503, content=health)
        return health
    except Exception as e:
        logger.error(f"DB health check failed: {e}")
        raise HTTPException(status_code=500, detail=f"DB health check failed: {str(e)}")

# File upload endpoint
@api_router.post("/upload")
async def upload_document(
    file: UploadFile = File(...),
    document_type: str = Form("mvsr_evidence"),
):
    """
    Upload a document file and stage it for later ingestion

    Accepts PDF files and stores them without chunking until an ingest request is made
    """
    try:
        # Validate file type
        if not file.filename or not file.filename.lower().endswith('.pdf'):
            raise HTTPException(status_code=400, detail="Only PDF files are supported")

        original_filename = Path(file.filename).name
        content = await file.read()
        if not content:
            raise HTTPException(status_code=400, detail="Uploaded PDF is empty")

        staged_token = _create_staged_upload_token(original_filename)
        staged_record = _set_staged_upload(
            staged_token,
            content=content,
            filename=original_filename,
            document_type=document_type,
        )

        _set_ingestion_status(
            staged_token,
            "staged",
            phase="staged",
            message="File uploaded. Waiting for Upload documents.",
            document_type=document_type,
            filename=original_filename,
        )

        return UploadResponse(
            status="staged",
            message="File staged in memory. Click Upload to start chunking and store it in the database.",
            filename=original_filename,
            stored_filename=staged_record["filename"],
            stored_path=staged_token,
            document_type=document_type,
            file_size=staged_record["file_size"],
            timestamp=datetime.now().isoformat(),
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"File upload failed: {e}")
        raise HTTPException(status_code=500, detail=f"Upload failed: {str(e)}")


@api_router.delete("/upload")
async def delete_staged_upload(request: StagedUploadDeleteRequest):
    """Delete a staged upload that has not yet been ingested."""
    try:
        stored_path = _normalize_ingestion_path(request.stored_path)

        if _is_staged_upload_token(stored_path):
            _remove_staged_upload(stored_path)
            _remove_ingestion_status(stored_path)
            return {
                "status": "deleted",
                "message": "Staged upload removed",
                "stored_path": stored_path,
                "timestamp": datetime.now().isoformat(),
            }

        legacy_upload_dir = (PROJECT_ROOT / "uploads").resolve()
        local_path = Path(stored_path).resolve()
        if legacy_upload_dir not in local_path.parents:
            raise HTTPException(status_code=400, detail="Invalid staged upload path")

        if local_path.exists():
            local_path.unlink()

        _remove_ingestion_status(str(local_path))

        return {
            "status": "deleted",
            "message": "Staged upload removed",
            "stored_path": str(local_path),
            "timestamp": datetime.now().isoformat(),
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to delete staged upload: {e}")
        raise HTTPException(status_code=500, detail=f"Delete failed: {str(e)}")


# ─── Auth Endpoints ────────────────────────────────────────────────────────

@api_router.post("/auth/login", response_model=LoginResponse)
async def login(request: LoginRequest):
    """
    Authenticate with username + password.\n
    Demo credentials: admin / naac2025 | faculty / mvsr@faculty | demo / demo1234
    """
    token = authenticate(request.username, request.password)
    if token is None:
        raise HTTPException(status_code=401, detail="Invalid username or password")
    info = get_session_info(token)
    return LoginResponse(
        token=token,
        username=info["username"],
        expires_at=info["expires_at"],
        message="Login successful",
    )

@api_router.post("/auth/logout")
async def logout_endpoint(token: str = None):
    """Invalidate a session token."""
    if token:
        logout(token)
    return {"status": "ok", "message": "Logged out"}

@api_router.get("/auth/me")
async def me(token: str = None):
    """Return session info for a valid token (used by frontend to rehydrate auth state)."""
    if not token:
        raise HTTPException(status_code=401, detail="No token provided")
    info = get_session_info(token)
    if info is None:
        raise HTTPException(status_code=401, detail="Invalid or expired token")
    return info

# Expose key endpoints without the /api prefix for local probes and misconfigured proxies
app.add_api_route("/health", health_check, methods=["GET"])
app.add_api_route("/stats", get_system_statistics, methods=["GET"])
app.add_api_route("/scheduler/status", get_scheduler_status, methods=["GET"])
app.add_api_route("/query", query_compliance, methods=["POST"])
app.add_api_route("/db/health", get_db_health, methods=["GET"])
app.add_api_route("/upload", upload_document, methods=["POST"])
app.add_api_route("/upload", delete_staged_upload, methods=["DELETE"])
app.add_api_route("/ingest", ingest_documents, methods=["POST"])
app.add_api_route("/ingest/status", get_ingest_status, methods=["POST"])
app.add_api_route("/auth/login", login, methods=["POST"])
app.add_api_route("/auth/logout", logout_endpoint, methods=["POST"])
app.add_api_route("/auth/me", me, methods=["GET"])

# Include the API router in the main app
app.include_router(api_router)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        app, 
        host=settings.host, 
        port=settings.port,
        reload=settings.reload,
        log_level=settings.log_level.lower()
    )
