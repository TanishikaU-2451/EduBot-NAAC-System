"""
Auto-Ingest Coordinator for NAAC Compliance Intelligence System
Orchestrates the complete auto-update pipeline from detection to knowledge base integration
"""

import logging
from typing import Dict, Any, List, Optional
from datetime import datetime, timedelta
import asyncio
from dataclasses import dataclass, asdict
import json
from pathlib import Path

from .naac_watcher import NAACWebsiteWatcher, WatchResult, DocumentInfo
from .downloader import NAACDocumentDownloader, DownloadResult
from .version_manager import NAACVersionManager, UpdateOperation
from ..db.chroma_store import ChromaVectorStore
from ..ingestion.ingest import DocumentIngestionPipeline

logger = logging.getLogger(__name__)

@dataclass
class AutoIngestReport:
    """Comprehensive report of auto-ingest operation"""
    operation_id: str
    timestamp: str
    duration_seconds: float
    
    # Watch phase
    documents_detected: int
    new_documents_found: int
    updated_documents_found: int
    
    # Download phase
    download_attempts: int
    successful_downloads: int
    failed_downloads: int
    
    # Version management phase
    new_versions_created: int
    documents_updated: int
    
    # Knowledge base phase
    knowledge_base_updates: int
    ingestion_failures: int
    
    # Overall status
    success: bool
    error_messages: List[str]
    
    # Detailed results
    watch_result: Optional[WatchResult] = None
    download_results: Optional[List[DownloadResult]] = None
    version_operations: Optional[List[UpdateOperation]] = None

class NAACAutoIngest:
    """
    Coordinates the complete auto-update pipeline for NAAC documents
    Handles detection, download, versioning, and knowledge base integration
    """
    
    def __init__(self,
                 data_dir: str = "./data",
                 cache_dir: str = "./cache", 
                 chroma_store: Optional[ChromaVectorStore] = None,
                 ingestion_pipeline: Optional[DocumentIngestionPipeline] = None,
                 config: Optional[Dict[str, Any]] = None):
        """
        Initialize auto-ingest coordinator
        
        Args:
            data_dir: Base directory for data storage
            cache_dir: Directory for caching
            chroma_store: ChromaDB vector store
            ingestion_pipeline: Document ingestion pipeline
            config: Configuration options
        """
        self.data_dir = Path(data_dir)
        self.cache_dir = Path(cache_dir)
        self.chroma_store = chroma_store
        self.ingestion_pipeline = ingestion_pipeline
        
        # Create directories
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        
        # Load configuration
        self.config = self._load_config(config)
        
        # Initialize components
        self.watcher = NAACWebsiteWatcher(
            cache_dir=str(self.cache_dir / "naac_watch"),
            user_agent=self.config.get('user_agent', 'NAAC-AutoIngest/1.0')
        )
        
        self.downloader = NAACDocumentDownloader(
            download_dir=str(self.data_dir / "naac_downloads"),
            max_concurrent_downloads=self.config.get('max_concurrent_downloads', 3),
            timeout=self.config.get('download_timeout', 300)
        )
        
        self.version_manager = NAACVersionManager(
            storage_dir=str(self.data_dir / "naac_versions"),
            chroma_store=chroma_store,
            ingestion_pipeline=ingestion_pipeline,
            max_versions_per_document=self.config.get('max_versions_per_document', 5)
        )
        
        # Operation history
        self.operation_history = self._load_operation_history()
        
        # Progress callbacks
        self.progress_callbacks = []
    
    def run_full_update_cycle(self, 
                            force_recheck: bool = False,
                            specific_criteria: Optional[List[str]] = None) -> AutoIngestReport:
        """
        Run complete auto-update cycle
        
        Args:
            force_recheck: Force recheck of all URLs even if recently checked
            specific_criteria: Only process documents for specific criteria
            
        Returns:
            Comprehensive report of the operation
        """
        operation_id = self._generate_operation_id()
        start_time = datetime.now()
        
        logger.info(f"Starting auto-ingest operation {operation_id}")
        
        # Initialize report
        report = AutoIngestReport(
            operation_id=operation_id,
            timestamp=start_time.isoformat(),
            duration_seconds=0.0,
            documents_detected=0,
            new_documents_found=0,
            updated_documents_found=0,
            download_attempts=0,
            successful_downloads=0,
            failed_downloads=0,
            new_versions_created=0,
            documents_updated=0,
            knowledge_base_updates=0,
            ingestion_failures=0,
            success=False,
            error_messages=[]
        )
        
        try:
            # Phase 1: Watch for document updates
            logger.info("Phase 1: Checking NAAC website for updates")
            watch_result = self._run_watch_phase(force_recheck)
            report.watch_result = watch_result
            
            if not watch_result.success:
                report.error_messages.extend(watch_result.errors)
                return self._finalize_report(report, start_time)
            
            # Update report with watch results
            report.documents_detected = watch_result.total_documents_found
            report.new_documents_found = len(watch_result.new_documents)
            report.updated_documents_found = len(watch_result.updated_documents)
            
            # Filter by criteria if specified
            documents_to_process = watch_result.new_documents + watch_result.updated_documents
            if specific_criteria:
                documents_to_process = [
                    doc for doc in documents_to_process 
                    if doc.criterion in specific_criteria
                ]
            
            if not documents_to_process:
                logger.info("No documents to process - auto-ingest complete")
                report.success = True
                return self._finalize_report(report, start_time)
            
            # Phase 2: Download new and updated documents
            logger.info(f"Phase 2: Downloading {len(documents_to_process)} documents")
            download_results = self._run_download_phase(documents_to_process)
            report.download_results = download_results
            
            # Update report with download results
            report.download_attempts = len(documents_to_process)
            report.successful_downloads = len([r for r in download_results if r.success])
            report.failed_downloads = len([r for r in download_results if not r.success])
            
            # Phase 3: Version management and knowledge base updates
            successful_downloads = [r for r in download_results if r.success]
            if successful_downloads:
                logger.info(f"Phase 3: Processing {len(successful_downloads)} successful downloads")
                version_report = self._run_version_management_phase(successful_downloads)
                
                # Update report with version management results
                report.new_versions_created = version_report.get('new_documents', 0)
                report.documents_updated = version_report.get('updated_documents', 0)
                report.knowledge_base_updates = len(version_report.get('knowledge_base_updates', []))
                report.ingestion_failures = version_report.get('failed_operations', 0)
            
            # Phase 4: Post-processing and cleanup
            logger.info("Phase 4: Post-processing and cleanup")
            self._run_cleanup_phase()
            
            report.success = True
            logger.info(f"Auto-ingest operation {operation_id} completed successfully")
            
        except Exception as e:
            logger.error(f"Error in auto-ingest operation {operation_id}: {e}")
            report.error_messages.append(str(e))
            report.success = False
        
        finally:
            # Finalize report and save operation history
            final_report = self._finalize_report(report, start_time)
            self._save_operation_to_history(final_report)
        
        return final_report
    
    def _run_watch_phase(self, force_recheck: bool = False) -> WatchResult:
        """Run the website watching phase"""
        
        try:
            # Check if we should skip watching based on recent check
            if not force_recheck and self._is_recent_check():
                logger.info("Skipping watch phase - recent check completed")
                return WatchResult(
                    timestamp=datetime.now().isoformat(),
                    total_documents_found=0,
                    new_documents=[],
                    updated_documents=[],
                    errors=[],
                    success=True
                )
            
            # Run the watcher
            watch_result = self.watcher.watch_for_updates(check_all_urls=True)
            
            # Notify progress callbacks
            self._notify_progress({
                'phase': 'watch',
                'documents_found': watch_result.total_documents_found,
                'new_documents': len(watch_result.new_documents),
                'updated_documents': len(watch_result.updated_documents)
            })
            
            return watch_result
            
        except Exception as e:
            logger.error(f"Error in watch phase: {e}")
            return WatchResult(
                timestamp=datetime.now().isoformat(),
                total_documents_found=0,
                new_documents=[],
                updated_documents=[],
                errors=[str(e)],
                success=False
            )
    
    def _run_download_phase(self, documents: List[DocumentInfo]) -> List[DownloadResult]:
        """Run the document download phase"""
        
        try:
            # Add progress callback to downloader
            def download_progress_callback(progress):
                self._notify_progress({
                    'phase': 'download',
                    'total_files': progress.total_files,
                    'completed_files': progress.completed_files,
                    'failed_files': progress.failed_files,
                    'current_file': progress.current_file
                })
            
            self.downloader.add_progress_callback(download_progress_callback)
            
            # Download documents
            download_results = self.downloader.download_documents(
                documents=documents,
                overwrite=self.config.get('overwrite_existing', False),
                organize_by_criterion=True
            )
            
            return download_results
            
        except Exception as e:
            logger.error(f"Error in download phase: {e}")
            # Return failed results for all documents
            return [
                DownloadResult(
                    document_info=doc,
                    success=False,
                    error_message=str(e)
                ) for doc in documents
            ]
    
    def _run_version_management_phase(self, download_results: List[DownloadResult]) -> Dict[str, Any]:
        """Run the version management and knowledge base update phase"""
        
        try:
            # Process documents through version manager
            version_report = self.version_manager.process_document_updates(download_results)
            
            # Notify progress
            self._notify_progress({
                'phase': 'version_management',
                'new_documents': version_report.get('new_documents', 0),
                'updated_documents': version_report.get('updated_documents', 0),
                'knowledge_base_updates': len(version_report.get('knowledge_base_updates', []))
            })
            
            return version_report
            
        except Exception as e:
            logger.error(f"Error in version management phase: {e}")
            return {
                'new_documents': 0,
                'updated_documents': 0,
                'failed_operations': len(download_results),
                'knowledge_base_updates': []
            }
    
    def _run_cleanup_phase(self):
        """Run post-processing cleanup"""
        
        try:
            # Clean up old downloads if configured
            if self.config.get('cleanup_old_downloads', False):
                cleanup_days = self.config.get('cleanup_days', 30)
                self.downloader.cleanup_old_downloads(cleanup_days)
            
            # Clean up temporary files
            temp_dir = self.cache_dir / "temp"
            if temp_dir.exists():
                import shutil
                shutil.rmtree(temp_dir, ignore_errors=True)
            
            logger.debug("Cleanup phase completed")
            
        except Exception as e:
            logger.warning(f"Error in cleanup phase: {e}")
    
    def run_incremental_update(self) -> AutoIngestReport:
        """Run incremental update (only check for new/updated documents)"""
        
        return self.run_full_update_cycle(
            force_recheck=False,
            specific_criteria=None
        )
    
    def run_criterion_specific_update(self, criteria: List[str]) -> AutoIngestReport:
        """Run update for specific NAAC criteria only"""
        
        return self.run_full_update_cycle(
            force_recheck=True,
            specific_criteria=criteria
        )
    
    def force_full_update(self) -> AutoIngestReport:
        """Force complete update of all documents"""
        
        return self.run_full_update_cycle(
            force_recheck=True,
            specific_criteria=None
        )
    
    def get_update_status(self) -> Dict[str, Any]:
        """Get current update status and statistics"""
        
        # Get statistics from all components
        watcher_stats = self.watcher.get_watch_statistics()
        downloader_stats = self.downloader.get_download_statistics()
        version_stats = self.version_manager.get_version_statistics()
        
        # Recent operations
        recent_operations = [
            op for op in self.operation_history[-10:]  # Last 10 operations
        ]
        
        # Last successful update
        last_success = None
        for op in reversed(self.operation_history):
            if op.get('success', False):
                last_success = op.get('timestamp')
                break
        
        return {
            'last_successful_update': last_success,
            'recent_operations': recent_operations,
            'component_statistics': {
                'watcher': watcher_stats,
                'downloader': downloader_stats,
                'version_manager': version_stats
            },
            'system_status': 'healthy' if last_success else 'needs_attention',
            'configuration': self.config
        }
    
    def schedule_next_update(self) -> datetime:
        """Calculate when the next update should run"""
        
        update_interval_hours = self.config.get('update_interval_hours', 24)
        
        # Find last successful update
        last_update = None
        for op in reversed(self.operation_history):
            if op.get('success', False):
                last_update = datetime.fromisoformat(op['timestamp'])
                break
        
        if last_update:
            next_update = last_update + timedelta(hours=update_interval_hours)
        else:
            next_update = datetime.now() + timedelta(hours=1)  # Run soon if never run
        
        return next_update
    
    def add_progress_callback(self, callback):
        """Add callback for progress notifications"""
        self.progress_callbacks.append(callback)
    
    def _notify_progress(self, progress_data: Dict[str, Any]):
        """Notify all progress callbacks"""
        for callback in self.progress_callbacks:
            try:
                callback(progress_data)
            except Exception as e:
                logger.error(f"Error in progress callback: {e}")
    
    def _is_recent_check(self) -> bool:
        """Check if a recent watch operation was completed"""
        
        cutoff_time = datetime.now() - timedelta(hours=self.config.get('min_check_interval_hours', 6))
        
        for operation in reversed(self.operation_history):
            if (operation.get('success', False) and 
                operation.get('documents_detected', 0) >= 0):  # Any successful watch
                op_time = datetime.fromisoformat(operation['timestamp'])
                if op_time > cutoff_time:
                    return True
        
        return False
    
    def _generate_operation_id(self) -> str:
        """Generate unique operation ID"""
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        return f"autoingest_{timestamp}"
    
    def _finalize_report(self, report: AutoIngestReport, start_time: datetime) -> AutoIngestReport:
        """Finalize the report with duration and final status"""
        
        end_time = datetime.now()
        report.duration_seconds = (end_time - start_time).total_seconds()
        
        return report
    
    def _save_operation_to_history(self, report: AutoIngestReport):
        """Save operation report to history"""
        
        # Convert report to dictionary (excluding large data structures)
        history_entry = asdict(report)
        
        # Remove large nested objects to keep history manageable
        history_entry.pop('watch_result', None)
        history_entry.pop('download_results', None) 
        history_entry.pop('version_operations', None)
        
        self.operation_history.append(history_entry)
        
        # Keep only last 100 operations
        if len(self.operation_history) > 100:
            self.operation_history = self.operation_history[-100:]
        
        self._save_operation_history()
    
    def _load_config(self, config: Optional[Dict[str, Any]]) -> Dict[str, Any]:
        """Load configuration with defaults"""
        
        default_config = {
            'update_interval_hours': 24,
            'min_check_interval_hours': 6,
            'max_concurrent_downloads': 3,
            'download_timeout': 300,
            'max_versions_per_document': 5,
            'overwrite_existing': False,
            'cleanup_old_downloads': True,
            'cleanup_days': 30,
            'user_agent': 'NAAC-AutoIngest/1.0'
        }
        
        if config:
            default_config.update(config)
        
        return default_config
    
    def _load_operation_history(self) -> List[Dict[str, Any]]:
        """Load operation history from file"""
        
        history_file = self.cache_dir / "operation_history.json"
        
        if history_file.exists():
            try:
                with open(history_file, 'r') as f:
                    return json.load(f)
            except Exception as e:
                logger.warning(f"Error loading operation history: {e}")
        
        return []
    
    def _save_operation_history(self):
        """Save operation history to file"""
        
        history_file = self.cache_dir / "operation_history.json"
        
        try:
            with open(history_file, 'w') as f:
                json.dump(self.operation_history, f, indent=2)
        except Exception as e:
            logger.error(f"Error saving operation history: {e}")