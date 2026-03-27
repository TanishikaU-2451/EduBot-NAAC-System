"""
FastAPI Main Application for NAAC Compliance Intelligence System
Provides REST API endpoints for the complete RAG pipeline and auto-update system
"""

from fastapi import FastAPI, HTTPException, BackgroundTasks, Depends, UploadFile, File, Form, APIRouter
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from typing import Dict, Any, List, Optional, Union
import logging
import asyncio
from datetime import datetime
from pathlib import Path
import os
import io
from contextlib import asynccontextmanager

try:
    from pdfminer.high_level import extract_text as pdf_extract_text
    PDF_SUPPORT = True
except ImportError:
    PDF_SUPPORT = False

# Import our system components
from ..rag.pipeline import RAGPipeline
from ..rag.metadata_mapper import NAACMetadataMapper
from ..db.supabase_store import SupabaseVectorStore
from ..llm.huggingface_client import HuggingFaceClient
from ..memory.memory_store import ConversationMemoryStore, MemoryIdentity
from ..ingestion.ingest import DocumentIngestionPipeline
from ..updater.auto_ingest import NAACAutoIngest
from ..scheduler.update_scheduler import NAACUpdateScheduler
from ..config.settings import get_settings

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
vector_store_instance: Optional[SupabaseVectorStore] = None
memory_store_instance: Optional[ConversationMemoryStore] = None

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
    file_paths: List[str] = Field(..., description="List of file paths to ingest")
    force_reingest: bool = Field(False, description="Force reingest of existing documents")
    additional_metadata: Optional[Dict[str, Any]] = Field(None, description="Additional metadata")

class UpdateRequest(BaseModel):
    update_type: str = Field("incremental", description="Update type: 'incremental', 'full', 'criterion'")
    criteria: Optional[List[str]] = Field(None, description="Specific criteria for criterion updates")
    force_check: bool = Field(False, description="Force check even if recently updated")

class ScheduleRequest(BaseModel):
    job_type: str = Field(..., description="Job type: 'daily', 'interval', 'criterion'")
    schedule: str = Field(..., description="Cron expression or interval specification")
    criteria: Optional[List[str]] = Field(None, description="Criteria for criterion-specific jobs")
    enabled: bool = Field(True, description="Whether job should be enabled")

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

# System initialization functions
def _ingest_markdown_docs(vector_store, data_dir: Path) -> None:
    """Ingest markdown/text documents into the vector store if empty."""
    try:
        def split_text_chunks(text: str, chunk_size: int, overlap: int) -> List[str]:
            cleaned = " ".join((text or "").split())
            if not cleaned:
                return []

            if len(cleaned) <= chunk_size:
                return [cleaned]

            chunks: List[str] = []
            start = 0
            step = max(chunk_size - overlap, 1)
            while start < len(cleaned):
                end = start + chunk_size
                chunk = cleaned[start:end].strip()
                if chunk:
                    chunks.append(chunk)
                if end >= len(cleaned):
                    break
                start += step
            return chunks

        chunk_size = max(settings.chunk_size, 400)
        chunk_overlap = max(min(settings.chunk_overlap, chunk_size // 2), 50)

        # Check if already populated
        stats = vector_store.get_collection_stats()
        naac_count = stats.get("naac_requirements_count", 0)
        mvsr_count = stats.get("mvsr_evidence_count", 0)
        if naac_count > 0 and mvsr_count > 0:
            logger.info(f"Collections already have data: {naac_count} NAAC, {mvsr_count} MVSR docs. Skipping ingestion.")
            return

        # Ingest NAAC documents
        naac_dir = data_dir / "naac_documents"
        naac_docs: List[str] = []
        naac_metas: List[Dict[str, Any]] = []
        if naac_dir.exists():
            for f in naac_dir.glob("*"):
                if f.suffix.lower() in {".md", ".txt"}:
                    text = f.read_text(encoding="utf-8", errors="ignore")
                    criterion = "1"
                    for c in ["1","2","3","4","5","6","7"]:
                        if f"criterion_{c}" in f.name.lower() or f"criteria_{c}" in f.name.lower():
                            criterion = c; break
                    for chunk_idx, chunk_text in enumerate(split_text_chunks(text, chunk_size, chunk_overlap)):
                        naac_docs.append(chunk_text)
                        naac_metas.append({
                            "type": "requirement",
                            "criterion": criterion,
                            "version": "2025",
                            "source_file": f.name,
                            "indicator": f"{criterion}.1",
                            "chunk_index": chunk_idx,
                            "storage_mode": "chunk_row",
                        })

        if naac_docs:
            vector_store.add_naac_documents(naac_docs, naac_metas)
            logger.info("Ingested startup NAAC corpus as %s chunk rows", len(naac_docs))

        # Ingest MVSR SSR PDF from mvsr_evidence/reports/
        ssr_dir = data_dir / "mvsr_evidence" / "reports"
        ssr_ingested = False
        mvsr_docs: List[str] = []
        mvsr_metas: List[Dict[str, Any]] = []
        if ssr_dir.exists() and PDF_SUPPORT:
            for f in ssr_dir.glob("*.pdf"):
                try:
                    text = pdf_extract_text(str(f))
                    if not text or not text.strip():
                        logger.warning(f"No text extracted from SSR PDF: {f.name}")
                        continue
                    for chunk_idx, chunk_text in enumerate(split_text_chunks(text, chunk_size, chunk_overlap)):
                        mvsr_docs.append(chunk_text)
                        mvsr_metas.append({
                            "type": "evidence",
                            "criterion": "1",
                            "document": f.stem.replace("-", " ").replace("_", " "),
                            "year": 2019,
                            "category": "ssr",
                            "source_file": f.name,
                            "chunk_index": chunk_idx,
                            "storage_mode": "chunk_row",
                        })
                    logger.info("Prepared MVSR SSR PDF for aggregated ingest: %s", f.name)
                    ssr_ingested = True
                except Exception as pdf_err:
                    logger.error(f"Failed to extract PDF {f.name}: {pdf_err}")
        elif not PDF_SUPPORT:
            logger.warning("pdfminer not available; falling back to MVSR markdown files")

        # Fallback to MVSR markdown files only if SSR PDF was not ingested
        if not ssr_ingested:
            mvsr_dir = data_dir / "mvsr_documents"
            if mvsr_dir.exists():
                for f in mvsr_dir.glob("*"):
                    if f.suffix.lower() in {".md", ".txt"}:
                        text = f.read_text(encoding="utf-8", errors="ignore")
                        category = "general"
                        if "research" in f.name.lower():
                            category = "research"
                        elif "academic" in f.name.lower():
                            category = "academic"
                        for chunk_idx, chunk_text in enumerate(split_text_chunks(text, chunk_size, chunk_overlap)):
                            mvsr_docs.append(chunk_text)
                            mvsr_metas.append({
                                "type": "evidence",
                                "criterion": "1",
                                "document": f.stem.replace("_", " "),
                                "year": 2024,
                                "category": category,
                                "source_file": f.name,
                                "chunk_index": chunk_idx,
                                "storage_mode": "chunk_row",
                            })
                        logger.info("Prepared MVSR fallback file for aggregated ingest: %s", f.name)

        if mvsr_docs:
            vector_store.add_mvsr_documents(mvsr_docs, mvsr_metas)
            logger.info("Ingested startup MVSR corpus as %s chunk rows", len(mvsr_docs))

        logger.info("Startup document ingestion complete.")
    except Exception as e:
        logger.error(f"Startup ingestion failed (non-fatal): {e}")


async def initialize_system():
    """Initialize all system components"""
    global rag_pipeline, auto_ingest, scheduler, metadata_mapper, vector_store_instance, memory_store_instance
    
    try:
        # Initialize Supabase vector store
        if not settings.supabase_db_url:
            raise ValueError("SUPABASE_DB_URL is required for Supabase vector backend")

        vector_store = SupabaseVectorStore(
            db_url=settings.supabase_db_url,
            table_name=settings.supabase_table,
            embedding_model=settings.embedding_model,
            embedding_dim=settings.embedding_dim,
            embedding_device=settings.embedding_device,
        )
        vector_store_instance = vector_store

        if settings.memory_enabled:
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
            memory_store_instance = memory_store
        else:
            memory_store_instance = None
        
        # Initialize Hugging Face client
        llm_client = HuggingFaceClient(
            model_name=settings.hf_model,
            api_token=settings.hf_api_token,
            timeout=settings.hf_timeout,
        )
        
        # Initialize ingestion pipeline
        ingestion_pipeline = DocumentIngestionPipeline(
            vector_store=vector_store,
            chunk_size=settings.chunk_size,
            chunk_overlap=settings.chunk_overlap,
        )
        
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
            },
        )
        
        # Initialize auto-ingest system
        auto_ingest = NAACAutoIngest(
            data_dir=str(settings.get_data_path()),
            cache_dir=str(settings.get_cache_path()),
            chroma_store=vector_store,
            ingestion_pipeline=ingestion_pipeline
        )
        
        # Initialize scheduler
        scheduler = NAACUpdateScheduler(auto_ingest=auto_ingest)
        
        # Initialize metadata mapper
        metadata_mapper = NAACMetadataMapper()
        
        # Start scheduler
        scheduler.start()
        
        # Ingest markdown knowledge base docs if collections are empty
        await asyncio.to_thread(_ingest_markdown_docs, vector_store, settings.get_data_path())
        
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


def get_vector_store() -> SupabaseVectorStore:
    """Dependency to get vector store"""
    if vector_store_instance is None:
        raise HTTPException(status_code=503, detail="Vector store not initialized")
    return vector_store_instance


def get_memory_store() -> Optional[ConversationMemoryStore]:
    """Dependency to get memory store (optional)."""
    return memory_store_instance


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

# API Endpoints

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
        
    except Exception as e:
        logger.error(f"Query processing failed: {e}")
        raise HTTPException(status_code=500, detail=f"Query processing failed: {str(e)}")

@api_router.post("/ingest")
async def ingest_documents(
    request: IngestRequest,
    background_tasks: BackgroundTasks,
    auto_ingest_system: NAACAutoIngest = Depends(get_auto_ingest)
):
    """
    Ingest documents into the knowledge base
    
    Process PDF documents and add them to the vector store
    """
    try:
        def run_ingestion():
            """Background task for document ingestion"""
            try:
                ingestion_pipeline = auto_ingest_system.ingestion_pipeline
                
                results = []
                for file_path in request.file_paths:
                    if not Path(file_path).exists():
                        results.append({
                            "file": file_path,
                            "status": "failed",
                            "error": "File not found"
                        })
                        continue
                    
                    result = ingestion_pipeline.ingest_single_document(
                        file_path=file_path,
                        document_type=request.document_type,
                        additional_metadata=request.additional_metadata
                    )
                    results.append(result)
                
                logger.info(f"Ingestion completed: {len(results)} documents processed")
                
            except Exception as e:
                logger.error(f"Background ingestion failed: {e}")
        
        # Start background ingestion
        background_tasks.add_task(run_ingestion)
        
        return {
            "status": "accepted",
            "message": f"Ingestion started for {len(request.file_paths)} documents",
            "document_type": request.document_type,
            "timestamp": datetime.now().isoformat()
        }
        
    except Exception as e:
        logger.error(f"Ingestion request failed: {e}")
        raise HTTPException(status_code=500, detail=f"Ingestion failed: {str(e)}")

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
async def get_last_sync(auto_ingest_system: NAACAutoIngest = Depends(get_auto_ingest)):
    """
    Get information about the last synchronization
    
    Returns details about the most recent update operation
    """
    try:
        status = auto_ingest_system.get_update_status()
        
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
async def get_scheduler_status(scheduler_system: NAACUpdateScheduler = Depends(get_scheduler)):
    """Get scheduler status and job information"""
    try:
        status = scheduler_system.get_scheduler_status()
        jobs = scheduler_system.get_job_list()

        # Calculate uptime hours
        uptime_hours = 0.0
        if scheduler_system.start_time and status.is_running:
            uptime_delta = datetime.now() - scheduler_system.start_time
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
    auto_ingest_system: NAACAutoIngest = Depends(get_auto_ingest)
):
    """Get comprehensive system statistics"""
    try:
        pipeline_stats = pipeline.get_pipeline_stats()
        update_status = auto_ingest_system.get_update_status()
        
        return {
            "pipeline_statistics": pipeline_stats,
            "update_status": update_status,
            "timestamp": datetime.now().isoformat()
        }
        
    except Exception as e:
        logger.error(f"Statistics request failed: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get statistics: {str(e)}")


@api_router.get("/db/health")
async def get_db_health(vector_store: SupabaseVectorStore = Depends(get_vector_store)):
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
    background_tasks: BackgroundTasks = BackgroundTasks(),
    auto_ingest_system: NAACAutoIngest = Depends(get_auto_ingest)
):
    """
    Upload and ingest a document file
    
    Accepts PDF files for immediate ingestion
    """
    try:
        # Validate file type
        if not file.filename.lower().endswith('.pdf'):
            raise HTTPException(status_code=400, detail="Only PDF files are supported")
        
        # Create upload directory
        upload_dir = settings.get_uploads_path()
        
        # Save uploaded file
        file_path = upload_dir / file.filename
        
        with open(file_path, "wb") as buffer:
            content = await file.read()
            buffer.write(content)
        
        # Start background ingestion
        def run_upload_ingestion():
            try:
                result = auto_ingest_system.ingestion_pipeline.ingest_single_document(
                    file_path=str(file_path),
                    document_type=document_type
                )
                logger.info(f"Upload ingestion completed: {file.filename}")
            except Exception as e:
                logger.error(f"Upload ingestion failed: {e}")
        
        background_tasks.add_task(run_upload_ingestion)
        
        return {
            "status": "accepted",
            "message": f"File uploaded and ingestion started",
            "filename": file.filename,
            "document_type": document_type,
            "file_size": len(content),
            "timestamp": datetime.now().isoformat()
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"File upload failed: {e}")
        raise HTTPException(status_code=500, detail=f"Upload failed: {str(e)}")

# Expose key endpoints without the /api prefix for local probes and misconfigured proxies
app.add_api_route("/health", health_check, methods=["GET"])
app.add_api_route("/stats", get_system_statistics, methods=["GET"])
app.add_api_route("/scheduler/status", get_scheduler_status, methods=["GET"])
app.add_api_route("/query", query_compliance, methods=["POST"])
app.add_api_route("/db/health", get_db_health, methods=["GET"])
app.add_api_route("/upload", upload_document, methods=["POST"])

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
