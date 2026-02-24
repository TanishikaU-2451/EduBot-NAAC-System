"""
FastAPI Main Application for NAAC Compliance Intelligence System
Provides REST API endpoints for the complete RAG pipeline and auto-update system
"""

from fastapi import FastAPI, HTTPException, BackgroundTasks, Depends, UploadFile, File, APIRouter
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from typing import Dict, Any, List, Optional, Union
import logging
import asyncio
from datetime import datetime
from pathlib import Path
import os
from contextlib import asynccontextmanager

# Import our system components
from ..rag.pipeline import RAGPipeline
from ..rag.metadata_mapper import NAACMetadataMapper
from ..db.chroma_store import ChromaVectorStore
from ..llm.ollama_client import OllamaClient
from ..ingestion.ingest import DocumentIngestionPipeline
from ..updater.auto_ingest import NAACAutoIngest
from ..scheduler.update_scheduler import NAACUpdateScheduler
from ..config.settings import get_settings

# Get application settings
settings = get_settings()

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Global system components (initialized on startup)
rag_pipeline: Optional[RAGPipeline] = None
auto_ingest: Optional[NAACAutoIngest] = None
scheduler: Optional[NAACUpdateScheduler] = None
metadata_mapper: Optional[NAACMetadataMapper] = None

# Pydantic models for request/response
class QueryRequest(BaseModel):
    query: str = Field(..., description="Natural language query about NAAC compliance")
    filters: Optional[Dict[str, Any]] = Field(None, description="Optional filters for retrieval")
    include_sources: bool = Field(True, description="Include source details in response")

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
def _ingest_markdown_docs(chroma_store: ChromaVectorStore, data_dir: Path) -> None:
    """Ingest markdown/text documents into ChromaDB if collections are empty."""
    try:
        # Check if already populated
        naac_count = chroma_store.naac_collection.count()
        mvsr_count = chroma_store.mvsr_collection.count()
        if naac_count > 0 and mvsr_count > 0:
            logger.info(f"Collections already have data: {naac_count} NAAC, {mvsr_count} MVSR docs. Skipping ingestion.")
            return

        def chunk_text(text: str, size: int = 800, overlap: int = 100) -> List[str]:
            words = text.split()
            chunks, i = [], 0
            while i < len(words):
                chunk = " ".join(words[i:i + size])
                if chunk.strip():
                    chunks.append(chunk)
                i += size - overlap
            return chunks

        # Ingest NAAC documents
        naac_dir = data_dir / "naac_documents"
        if naac_dir.exists():
            for f in naac_dir.glob("*"):
                if f.suffix.lower() in {".md", ".txt"}:
                    text = f.read_text(encoding="utf-8", errors="ignore")
                    chunks = chunk_text(text)
                    if not chunks:
                        continue
                    criterion = "1"
                    for c in ["1","2","3","4","5","6","7"]:
                        if f"criterion_{c}" in f.name.lower() or f"criteria_{c}" in f.name.lower():
                            criterion = c; break
                    metadatas = [{
                        "type": "requirement", "criterion": criterion,
                        "version": "2025", "source_file": f.name,
                        "indicator": f"{criterion}.1"
                    } for _ in chunks]
                    chroma_store.add_naac_documents(chunks, metadatas)
                    logger.info(f"Ingested NAAC file: {f.name} ({len(chunks)} chunks)")

        # Ingest MVSR documents
        mvsr_dir = data_dir / "mvsr_documents"
        if mvsr_dir.exists():
            for f in mvsr_dir.glob("*"):
                if f.suffix.lower() in {".md", ".txt"}:
                    text = f.read_text(encoding="utf-8", errors="ignore")
                    chunks = chunk_text(text)
                    if not chunks:
                        continue
                    category = "general"
                    if "research" in f.name.lower():
                        category = "research"
                    elif "academic" in f.name.lower():
                        category = "academic"
                    metadatas = [{
                        "type": "evidence", "criterion": "1",
                        "document": f.stem.replace("_", " "),
                        "year": 2024, "category": category,
                        "source_file": f.name
                    } for _ in chunks]
                    chroma_store.add_mvsr_documents(chunks, metadatas)
                    logger.info(f"Ingested MVSR file: {f.name} ({len(chunks)} chunks)")

        logger.info("Startup document ingestion complete.")
    except Exception as e:
        logger.error(f"Startup ingestion failed (non-fatal): {e}")


async def initialize_system():
    """Initialize all system components"""
    global rag_pipeline, auto_ingest, scheduler, metadata_mapper
    
    try:
        # Initialize ChromaDB
        chroma_store = ChromaVectorStore(persist_directory=str(settings.get_chroma_path()))
        
        # Initialize Ollama client
        ollama_client = OllamaClient(
            model_name=settings.ollama_model,
            host=settings.ollama_host
        )
        
        # Initialize ingestion pipeline
        ingestion_pipeline = DocumentIngestionPipeline(chroma_store=chroma_store)
        
        # Initialize RAG pipeline
        rag_pipeline = RAGPipeline(
            chroma_store=chroma_store,
            ollama_client=ollama_client
        )
        
        # Initialize auto-ingest system
        auto_ingest = NAACAutoIngest(
            data_dir=str(settings.get_data_path()),
            cache_dir=str(settings.get_cache_path()),
            chroma_store=chroma_store,
            ingestion_pipeline=ingestion_pipeline
        )
        
        # Initialize scheduler
        scheduler = NAACUpdateScheduler(auto_ingest=auto_ingest)
        
        # Initialize metadata mapper
        metadata_mapper = NAACMetadataMapper()
        
        # Start scheduler
        scheduler.start()
        
        # Ingest markdown knowledge base docs if collections are empty
        await asyncio.to_thread(_ingest_markdown_docs, chroma_store, settings.get_data_path())
        
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
                "metadata_mapper": metadata_mapper is not None
            }
        }
        
        # Check RAG pipeline health if available
        if rag_pipeline:
            pipeline_health = rag_pipeline.get_pipeline_health()
            health_status["pipeline_health"] = pipeline_health
            
            if pipeline_health.get("overall_status") != "healthy":
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
async def query_compliance(request: QueryRequest, pipeline: RAGPipeline = Depends(get_rag_pipeline)):
    """
    Query the NAAC compliance system
    
    Process natural language queries and return structured compliance analysis
    """
    try:
        logger.info(f"Processing query: {request.query[:100]}...")
        
        # Process query through RAG pipeline (run sync function in thread to avoid blocking)
        import asyncio
        response = await asyncio.to_thread(
            pipeline.process_query,
            request.query,
            request.filters
        )
        
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
        
        return {
            "scheduler_status": status,
            "jobs": jobs,
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

# File upload endpoint
@api_router.post("/upload")
async def upload_document(
    file: UploadFile = File(...),
    document_type: str = "mvsr_evidence",
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