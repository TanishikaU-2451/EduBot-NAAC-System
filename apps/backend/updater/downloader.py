"""
Document Downloader for NAAC Compliance Intelligence System
Handles downloading of NAAC documents with progress tracking and error handling
"""

import requests
import hashlib
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple, Callable
import logging
import time
from datetime import datetime
from dataclasses import dataclass, asdict
import shutil
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
import json

from .naac_watcher import DocumentInfo

logger = logging.getLogger(__name__)

@dataclass
class DownloadResult:
    """Result of a download operation"""
    document_info: DocumentInfo
    success: bool
    file_path: Optional[str] = None
    file_size: Optional[int] = None
    download_time: Optional[float] = None
    error_message: Optional[str] = None
    checksum: Optional[str] = None

@dataclass
class DownloadProgress:
    """Progress information for downloads"""
    total_files: int
    completed_files: int
    failed_files: int
    current_file: Optional[str] = None
    bytes_downloaded: int = 0
    total_bytes: int = 0
    start_time: Optional[datetime] = None

class NAACDocumentDownloader:
    """
    Downloads NAAC documents with progress tracking and error handling
    Supports concurrent downloads and resume capability
    """
    
    def __init__(self, 
                 download_dir: str = "./downloads/naac_documents",
                 max_concurrent_downloads: int = 3,
                 chunk_size: int = 8192,
                 timeout: int = 300):
        """
        Initialize document downloader
        
        Args:
            download_dir: Directory to save downloaded documents
            max_concurrent_downloads: Maximum number of concurrent downloads
            chunk_size: Size of download chunks in bytes
            timeout: Download timeout in seconds
        """
        self.download_dir = Path(download_dir)
        self.download_dir.mkdir(parents=True, exist_ok=True)
        
        self.max_concurrent_downloads = max_concurrent_downloads
        self.chunk_size = chunk_size
        self.timeout = timeout
        
        # Setup download session
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'NAAC-Compliance-System/1.0',
            'Accept': '*/*',
            'Accept-Encoding': 'gzip, deflate',
            'Connection': 'keep-alive'
        })
        
        # Progress tracking
        self.progress_callbacks: List[Callable[[DownloadProgress], None]] = []
        self.current_progress = DownloadProgress(0, 0, 0)
        
        # Download history
        self.download_history = self._load_download_history()
        
        # Lock for thread-safe operations
        self._lock = threading.Lock()
    
    def add_progress_callback(self, callback: Callable[[DownloadProgress], None]):
        """Add a callback function to receive progress updates"""
        self.progress_callbacks.append(callback)
    
    def download_documents(self, 
                          documents: List[DocumentInfo],
                          overwrite: bool = False,
                          organize_by_criterion: bool = True) -> List[DownloadResult]:
        """
        Download multiple documents
        
        Args:
            documents: List of documents to download
            overwrite: Whether to overwrite existing files
            organize_by_criterion: Whether to organize files by criterion
            
        Returns:
            List of download results
        """
        logger.info(f"Starting download of {len(documents)} documents")
        
        # Initialize progress tracking
        self.current_progress = DownloadProgress(
            total_files=len(documents),
            completed_files=0,
            failed_files=0,
            start_time=datetime.now()
        )
        
        # Filter out already downloaded documents if not overwriting
        documents_to_download = []
        if not overwrite:
            for doc in documents:
                existing_path = self._get_document_path(doc, organize_by_criterion)
                if not existing_path.exists():
                    documents_to_download.append(doc)
                else:
                    logger.info(f"Skipping existing file: {doc.title}")
        else:
            documents_to_download = documents
        
        logger.info(f"Downloading {len(documents_to_download)} documents (skipped {len(documents) - len(documents_to_download)} existing)")
        
        results = []
        
        # Use ThreadPoolExecutor for concurrent downloads
        with ThreadPoolExecutor(max_workers=self.max_concurrent_downloads) as executor:
            # Submit download tasks
            future_to_doc = {
                executor.submit(
                    self._download_single_document, 
                    doc, 
                    overwrite, 
                    organize_by_criterion
                ): doc 
                for doc in documents_to_download
            }
            
            # Process completed downloads
            for future in as_completed(future_to_doc):
                doc = future_to_doc[future]
                try:
                    result = future.result()
                    results.append(result)
                    
                    # Update progress
                    with self._lock:
                        if result.success:
                            self.current_progress.completed_files += 1
                        else:
                            self.current_progress.failed_files += 1
                        
                        self._notify_progress()
                    
                except Exception as e:
                    logger.error(f"Download failed for {doc.title}: {e}")
                    result = DownloadResult(
                        document_info=doc,
                        success=False,
                        error_message=str(e)
                    )
                    results.append(result)
                    
                    with self._lock:
                        self.current_progress.failed_files += 1
                        self._notify_progress()
        
        # Save download history
        self._update_download_history(results)
        
        total_time = (datetime.now() - self.current_progress.start_time).total_seconds()
        logger.info(f"Download completed in {total_time:.2f}s: {self.current_progress.completed_files} successful, {self.current_progress.failed_files} failed")
        
        return results
    
    def _download_single_document(self, 
                                 document: DocumentInfo,
                                 overwrite: bool,
                                 organize_by_criterion: bool) -> DownloadResult:
        """Download a single document"""
        
        start_time = time.time()
        
        try:
            # Update current file in progress
            with self._lock:
                self.current_progress.current_file = document.title
                self._notify_progress()
            
            # Determine download path
            file_path = self._get_document_path(document, organize_by_criterion)
            
            # Check if file exists and we shouldn't overwrite
            if file_path.exists() and not overwrite:
                logger.info(f"File already exists: {file_path}")
                return DownloadResult(
                    document_info=document,
                    success=True,
                    file_path=str(file_path),
                    file_size=file_path.stat().st_size,
                    download_time=0.0
                )
            
            # Create directory if it doesn't exist
            file_path.parent.mkdir(parents=True, exist_ok=True)
            
            # Download the file
            logger.info(f"Downloading: {document.title} -> {file_path}")
            
            response = self.session.get(document.url, timeout=self.timeout, stream=True)
            response.raise_for_status()
            
            # Get total file size
            total_size = int(response.headers.get('content-length', 0))
            
            # Download with progress tracking
            downloaded_size = 0
            checksum = hashlib.sha256()
            
            with open(file_path, 'wb') as f:
                for chunk in response.iter_content(chunk_size=self.chunk_size):
                    if chunk:
                        f.write(chunk)
                        checksum.update(chunk)
                        downloaded_size += len(chunk)
                        
                        # Update progress
                        with self._lock:
                            self.current_progress.bytes_downloaded += len(chunk)
                            if total_size > 0:
                                self.current_progress.total_bytes = total_size
                            self._notify_progress()
            
            download_time = time.time() - start_time
            final_checksum = checksum.hexdigest()[:16]
            
            logger.info(f"Downloaded successfully: {document.title} ({downloaded_size} bytes)")
            
            return DownloadResult(
                document_info=document,
                success=True,
                file_path=str(file_path),
                file_size=downloaded_size,
                download_time=download_time,
                checksum=final_checksum
            )
            
        except Exception as e:
            logger.error(f"Error downloading {document.title}: {e}")
            
            return DownloadResult(
                document_info=document,
                success=False,
                error_message=str(e),
                download_time=time.time() - start_time
            )
    
    def _get_document_path(self, 
                          document: DocumentInfo, 
                          organize_by_criterion: bool) -> Path:
        """Get the file path for a document"""
        
        # Generate safe filename
        safe_title = self._sanitize_filename(document.title)
        
        # Add file extension if not present
        if not safe_title.endswith(f'.{document.file_type}'):
            safe_title += f'.{document.file_type}'
        
        # Organize by criterion if specified
        if organize_by_criterion and document.criterion:
            criterion_dir = self.download_dir / f"criterion_{document.criterion}"
            return criterion_dir / safe_title
        else:
            return self.download_dir / safe_title
    
    def _sanitize_filename(self, filename: str) -> str:
        """Sanitize filename for filesystem"""
        
        # Remove or replace invalid characters
        invalid_chars = '<>:"/\\|?*'
        for char in invalid_chars:
            filename = filename.replace(char, '_')
        
        # Limit length
        if len(filename) > 200:
            filename = filename[:200]
        
        # Remove leading/trailing spaces and dots
        filename = filename.strip(' .')
        
        # Ensure filename is not empty
        if not filename:
            filename = f"naac_document_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        
        return filename
    
    def _notify_progress(self):
        """Notify all progress callbacks"""
        for callback in self.progress_callbacks:
            try:
                callback(self.current_progress)
            except Exception as e:
                logger.error(f"Error in progress callback: {e}")
    
    def download_single_document(self, 
                               document: DocumentInfo,
                               target_path: Optional[str] = None) -> DownloadResult:
        """
        Download a single document to a specific path
        
        Args:
            document: Document to download
            target_path: Specific path to save the file (optional)
            
        Returns:
            Download result
        """
        if target_path:
            # Override the path determination logic
            original_method = self._get_document_path
            self._get_document_path = lambda doc, organize: Path(target_path)
            
            try:
                result = self._download_single_document(document, False, False)
            finally:
                self._get_document_path = original_method
            
            return result
        else:
            return self._download_single_document(document, False, True)
    
    def resume_failed_downloads(self) -> List[DownloadResult]:
        """Resume previously failed downloads"""
        
        failed_downloads = []
        
        # Find failed downloads from history
        for entry in self.download_history:
            if not entry.get('success', True):
                # Recreate DocumentInfo from history
                doc_data = entry['document_info']
                document = DocumentInfo(**doc_data)
                failed_downloads.append(document)
        
        if failed_downloads:
            logger.info(f"Resuming {len(failed_downloads)} failed downloads")
            return self.download_documents(failed_downloads, overwrite=False)
        else:
            logger.info("No failed downloads to resume")
            return []
    
    def verify_downloads(self, results: List[DownloadResult]) -> Dict[str, Any]:
        """
        Verify integrity of downloaded files
        
        Args:
            results: List of download results to verify
            
        Returns:
            Verification report
        """
        logger.info(f"Verifying {len(results)} downloaded files")
        
        verification_report = {
            'total_files': len(results),
            'verified_files': 0,
            'corrupted_files': 0,
            'missing_files': 0,
            'details': []
        }
        
        for result in results:
            if not result.success or not result.file_path:
                continue
            
            file_path = Path(result.file_path)
            
            if not file_path.exists():
                verification_report['missing_files'] += 1
                verification_report['details'].append({
                    'file': result.document_info.title,
                    'status': 'missing',
                    'path': str(file_path)
                })
                continue
            
            # Verify file size
            actual_size = file_path.stat().st_size
            
            if result.file_size and actual_size != result.file_size:
                verification_report['corrupted_files'] += 1
                verification_report['details'].append({
                    'file': result.document_info.title,
                    'status': 'size_mismatch',
                    'expected_size': result.file_size,
                    'actual_size': actual_size
                })
                continue
            
            # File appears to be intact
            verification_report['verified_files'] += 1
            verification_report['details'].append({
                'file': result.document_info.title,
                'status': 'verified',
                'size': actual_size
            })
        
        logger.info(f"Verification completed: {verification_report['verified_files']} verified, "
                   f"{verification_report['corrupted_files']} corrupted, "
                   f"{verification_report['missing_files']} missing")
        
        return verification_report
    
    def _update_download_history(self, results: List[DownloadResult]):
        """Update download history"""
        
        for result in results:
            entry = {
                'timestamp': datetime.now().isoformat(),
                'document_info': asdict(result.document_info),
                'success': result.success,
                'file_path': result.file_path,
                'file_size': result.file_size,
                'download_time': result.download_time,
                'error_message': result.error_message,
                'checksum': result.checksum
            }
            self.download_history.append(entry)
        
        # Keep only last 1000 entries
        if len(self.download_history) > 1000:
            self.download_history = self.download_history[-1000:]
        
        self._save_download_history()
    
    def _load_download_history(self) -> List[Dict[str, Any]]:
        """Load download history from file"""
        
        history_file = self.download_dir / "download_history.json"
        
        if history_file.exists():
            try:
                with open(history_file, 'r') as f:
                    return json.load(f)
            except Exception as e:
                logger.warning(f"Error loading download history: {e}")
        
        return []
    
    def _save_download_history(self):
        """Save download history to file"""
        
        history_file = self.download_dir / "download_history.json"
        
        try:
            with open(history_file, 'w') as f:
                json.dump(self.download_history, f, indent=2)
        except Exception as e:
            logger.error(f"Error saving download history: {e}")
    
    def get_download_statistics(self) -> Dict[str, Any]:
        """Get download statistics"""
        
        total_downloads = len(self.download_history)
        successful_downloads = len([entry for entry in self.download_history if entry.get('success', False)])
        
        # Calculate total size downloaded
        total_size = sum(entry.get('file_size', 0) for entry in self.download_history if entry.get('success', False))
        
        # Get recent download activity (last 7 days)
        recent_cutoff = datetime.now().timestamp() - (7 * 24 * 60 * 60)
        recent_downloads = [
            entry for entry in self.download_history 
            if datetime.fromisoformat(entry['timestamp']).timestamp() > recent_cutoff
        ]
        
        return {
            'total_downloads': total_downloads,
            'successful_downloads': successful_downloads,
            'failed_downloads': total_downloads - successful_downloads,
            'success_rate': (successful_downloads / total_downloads * 100) if total_downloads > 0 else 0,
            'total_size_downloaded': total_size,
            'total_size_mb': round(total_size / (1024 * 1024), 2),
            'recent_downloads_7_days': len(recent_downloads),
            'download_directory': str(self.download_dir),
            'current_progress': asdict(self.current_progress) if hasattr(self, 'current_progress') else None
        }
    
    def cleanup_old_downloads(self, days_old: int = 30) -> Dict[str, Any]:
        """
        Clean up old download files
        
        Args:
            days_old: Delete files older than this many days
            
        Returns:
            Cleanup report
        """
        cutoff_time = datetime.now().timestamp() - (days_old * 24 * 60 * 60)
        
        cleanup_report = {
            'files_deleted': 0,
            'space_freed': 0,
            'errors': []
        }
        
        try:
            for file_path in self.download_dir.rglob('*'):
                if file_path.is_file():
                    # Check if file is old enough
                    if file_path.stat().st_mtime < cutoff_time:
                        try:
                            file_size = file_path.stat().st_size
                            file_path.unlink()
                            cleanup_report['files_deleted'] += 1
                            cleanup_report['space_freed'] += file_size
                        except Exception as e:
                            cleanup_report['errors'].append(f"Error deleting {file_path}: {e}")
        
        except Exception as e:
            cleanup_report['errors'].append(f"Error during cleanup: {e}")
        
        logger.info(f"Cleanup completed: {cleanup_report['files_deleted']} files deleted, "
                   f"{cleanup_report['space_freed'] / (1024*1024):.2f} MB freed")
        
        return cleanup_report