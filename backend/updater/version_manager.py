"""
Version Manager for NAAC Compliance Intelligence System
Handles versioning of NAAC documents and manages updates to the knowledge base
"""

import json
import hashlib
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple
import logging
from datetime import datetime, timedelta
from dataclasses import dataclass, asdict
import shutil
from collections import defaultdict

from .naac_watcher import DocumentInfo
from .downloader import DownloadResult
from ..db.chroma_store import ChromaVectorStore
from ..ingestion.ingest import DocumentIngestionPipeline

logger = logging.getLogger(__name__)

@dataclass
class DocumentVersion:
    """Information about a document version"""
    document_id: str
    version: str
    file_path: str
    checksum: str
    timestamp: str
    file_size: int
    is_current: bool
    metadata: Dict[str, Any]

@dataclass
class UpdateOperation:
    """Information about an update operation"""
    operation_id: str
    timestamp: str
    operation_type: str  # 'new_document', 'update_document', 'archive_version'
    document_info: DocumentInfo
    old_version: Optional[str] = None
    new_version: Optional[str] = None
    status: str = 'pending'  # 'pending', 'completed', 'failed'
    error_message: Optional[str] = None

class NAACVersionManager:
    """
    Manages versions of NAAC documents and coordinates updates to the knowledge base
    Handles document lifecycle, version archiving, and knowledge base synchronization
    """
    
    def __init__(self, 
                 storage_dir: str = "./naac_versions",
                 chroma_store: Optional[ChromaVectorStore] = None,
                 ingestion_pipeline: Optional[DocumentIngestionPipeline] = None,
                 max_versions_per_document: int = 5):
        """
        Initialize version manager
        
        Args:
            storage_dir: Directory to store versioned documents
            chroma_store: ChromaDB vector store for knowledge base updates
            ingestion_pipeline: Document ingestion pipeline
            max_versions_per_document: Maximum number of versions to keep per document
        """
        self.storage_dir = Path(storage_dir)
        self.storage_dir.mkdir(parents=True, exist_ok=True)
        
        self.chroma_store = chroma_store
        self.ingestion_pipeline = ingestion_pipeline
        self.max_versions_per_document = max_versions_per_document
        
        # Version tracking
        self.version_registry = self._load_version_registry()
        self.update_operations = self._load_update_operations()
        
        # Document ID mapping (URL hash -> document_id)
        self.document_id_mapping = self._build_document_id_mapping()
    
    def process_document_updates(self, 
                               download_results: List[DownloadResult]) -> Dict[str, Any]:
        """
        Process downloaded documents for version management and knowledge base updates
        
        Args:
            download_results: Results from document downloader
            
        Returns:
            Update report with processed documents and operations
        """
        logger.info(f"Processing {len(download_results)} documents for version management")
        
        update_report = {
            'timestamp': datetime.now().isoformat(),
            'total_documents': len(download_results),
            'new_documents': 0,
            'updated_documents': 0,
            'failed_operations': 0,
            'operations': [],
            'knowledge_base_updates': []
        }
        
        for result in download_results:
            if not result.success or not result.file_path:
                update_report['failed_operations'] += 1
                continue
                
            try:
                # Process the document
                operation = self._process_single_document(result)
                update_report['operations'].append(asdict(operation))
                
                if operation.status == 'completed':
                    if operation.operation_type == 'new_document':
                        update_report['new_documents'] += 1
                    elif operation.operation_type == 'update_document':
                        update_report['updated_documents'] += 1
                    
                    # Update knowledge base if components are available
                    if self.chroma_store and self.ingestion_pipeline:
                        kb_update = self._update_knowledge_base(operation)
                        if kb_update:
                            update_report['knowledge_base_updates'].append(kb_update)
                else:
                    update_report['failed_operations'] += 1
                    
            except Exception as e:
                logger.error(f"Error processing document {result.document_info.title}: {e}")
                update_report['failed_operations'] += 1
        
        # Save updated records
        self._save_version_registry()
        self._save_update_operations()
        
        logger.info(f"Version management completed: {update_report['new_documents']} new, "
                   f"{update_report['updated_documents']} updated, "
                   f"{update_report['failed_operations']} failed")
        
        return update_report
    
    def _process_single_document(self, result: DownloadResult) -> UpdateOperation:
        """Process a single downloaded document"""
        
        doc_info = result.document_info
        
        # Generate document ID
        document_id = self._generate_document_id(doc_info)
        
        # Calculate file checksum
        file_checksum = self._calculate_file_checksum(result.file_path)
        
        # Check if this is a new document or an update
        existing_versions = self._get_document_versions(document_id)
        
        if not existing_versions:
            # New document
            operation = self._handle_new_document(document_id, result, file_checksum)
        else:
            # Check if this is actually a new version
            if self._is_new_version(existing_versions, file_checksum):
                operation = self._handle_document_update(document_id, result, file_checksum, existing_versions)
            else:
                # Same version, no update needed
                operation = UpdateOperation(
                    operation_id=self._generate_operation_id(),
                    timestamp=datetime.now().isoformat(),
                    operation_type='no_change',
                    document_info=doc_info,
                    status='completed'
                )
        
        return operation
    
    def _handle_new_document(self, 
                           document_id: str, 
                           result: DownloadResult, 
                           file_checksum: str) -> UpdateOperation:
        """Handle processing of a new document"""
        
        try:
            # Create version entry
            version = "1.0"
            version_info = DocumentVersion(
                document_id=document_id,
                version=version,
                file_path=result.file_path,
                checksum=file_checksum,
                timestamp=datetime.now().isoformat(),
                file_size=result.file_size or 0,
                is_current=True,
                metadata=asdict(result.document_info)
            )
            
            # Store version
            if document_id not in self.version_registry:
                self.version_registry[document_id] = []
            self.version_registry[document_id].append(asdict(version_info))
            
            # Create versioned file copy
            versioned_path = self._create_versioned_file(document_id, version, result.file_path)
            
            operation = UpdateOperation(
                operation_id=self._generate_operation_id(),
                timestamp=datetime.now().isoformat(),
                operation_type='new_document',
                document_info=result.document_info,
                new_version=version,
                status='completed'
            )
            
            logger.info(f"New document registered: {result.document_info.title} (v{version})")
            
        except Exception as e:
            operation = UpdateOperation(
                operation_id=self._generate_operation_id(),
                timestamp=datetime.now().isoformat(),
                operation_type='new_document',
                document_info=result.document_info,
                status='failed',
                error_message=str(e)
            )
            logger.error(f"Failed to process new document: {e}")
        
        return operation
    
    def _handle_document_update(self, 
                              document_id: str, 
                              result: DownloadResult, 
                              file_checksum: str,
                              existing_versions: List[Dict[str, Any]]) -> UpdateOperation:
        """Handle processing of a document update"""
        
        try:
            # Mark previous version as not current
            for version_data in existing_versions:
                version_data['is_current'] = False
            
            # Generate new version number
            version_numbers = [float(v['version']) for v in existing_versions]
            new_version_num = max(version_numbers) + 0.1
            new_version = f"{new_version_num:.1f}"
            
            # Create new version entry
            version_info = DocumentVersion(
                document_id=document_id,
                version=new_version,
                file_path=result.file_path,
                checksum=file_checksum,
                timestamp=datetime.now().isoformat(),
                file_size=result.file_size or 0,
                is_current=True,
                metadata=asdict(result.document_info)
            )
            
            # Add to registry
            self.version_registry[document_id].append(asdict(version_info))
            
            # Create versioned file copy
            versioned_path = self._create_versioned_file(document_id, new_version, result.file_path)
            
            # Clean up old versions if necessary
            self._cleanup_old_versions(document_id)
            
            operation = UpdateOperation(
                operation_id=self._generate_operation_id(),
                timestamp=datetime.now().isoformat(),
                operation_type='update_document',
                document_info=result.document_info,
                old_version=existing_versions[-1]['version'] if existing_versions else None,
                new_version=new_version,
                status='completed'
            )
            
            logger.info(f"Document updated: {result.document_info.title} (v{new_version})")
            
        except Exception as e:
            operation = UpdateOperation(
                operation_id=self._generate_operation_id(),
                timestamp=datetime.now().isoformat(),
                operation_type='update_document',
                document_info=result.document_info,
                status='failed',
                error_message=str(e)
            )
            logger.error(f"Failed to process document update: {e}")
        
        return operation
    
    def _update_knowledge_base(self, operation: UpdateOperation) -> Optional[Dict[str, Any]]:
        """Update the knowledge base with new or updated documents"""
        
        if operation.status != 'completed':
            return None
        
        try:
            document_id = self._generate_document_id(operation.document_info)
            current_version = self._get_current_version(document_id)
            
            if not current_version:
                return None
            
            file_path = current_version['file_path']
            
            # If this is an update, archive old version in ChromaDB
            if operation.operation_type == 'update_document' and operation.old_version:
                self.chroma_store.update_naac_version(operation.old_version, operation.new_version)
            
            # Ingest the new/updated document
            additional_metadata = {
                'version': operation.new_version or '1.0',
                'document_id': document_id,
                'last_updated': operation.timestamp
            }
            
            ingest_result = self.ingestion_pipeline.ingest_single_document(
                file_path=file_path,
                document_type='naac_requirement',
                additional_metadata=additional_metadata
            )
            
            if ingest_result['status'] == 'success':
                kb_update = {
                    'document_id': document_id,
                    'operation_type': operation.operation_type,
                    'version': operation.new_version or '1.0', 
                    'chunks_created': ingest_result.get('chunks_created', 0),
                    'timestamp': datetime.now().isoformat()
                }
                
                logger.info(f"Knowledge base updated: {operation.document_info.title}")
                return kb_update
            else:
                logger.error(f"Failed to update knowledge base: {ingest_result.get('error', 'Unknown error')}")
                return None
                
        except Exception as e:
            logger.error(f"Error updating knowledge base: {e}")
            return None
    
    def _generate_document_id(self, doc_info: DocumentInfo) -> str:
        """Generate a unique document ID based on URL and title"""
        
        # Use URL as primary identifier, fallback to title
        identifier = doc_info.url if doc_info.url else doc_info.title
        
        # Create hash
        doc_hash = hashlib.md5(identifier.encode()).hexdigest()[:12]
        
        # Add criterion prefix if available
        if doc_info.criterion:
            return f"naac_c{doc_info.criterion}_{doc_hash}"
        else:
            return f"naac_{doc_hash}"
    
    def _calculate_file_checksum(self, file_path: str) -> str:
        """Calculate SHA-256 checksum of file"""
        
        hash_sha256 = hashlib.sha256()
        
        with open(file_path, "rb") as f:
            for chunk in iter(lambda: f.read(4096), b""):
                hash_sha256.update(chunk)
        
        return hash_sha256.hexdigest()[:16]
    
    def _get_document_versions(self, document_id: str) -> List[Dict[str, Any]]:
        """Get all versions for a document"""
        return self.version_registry.get(document_id, [])
    
    def _get_current_version(self, document_id: str) -> Optional[Dict[str, Any]]:
        """Get the current version of a document"""
        
        versions = self._get_document_versions(document_id)
        
        for version in versions:
            if version.get('is_current', False):
                return version
        
        # If no current version marked, return the latest
        if versions:
            return sorted(versions, key=lambda x: x['timestamp'])[-1]
        
        return None
    
    def _is_new_version(self, existing_versions: List[Dict[str, Any]], new_checksum: str) -> bool:
        """Check if a document represents a new version"""
        
        # Check if checksum matches any existing version
        for version in existing_versions:
            if version.get('checksum') == new_checksum:
                return False
        
        return True
    
    def _create_versioned_file(self, document_id: str, version: str, source_path: str) -> str:
        """Create a versioned copy of the file"""
        
        # Create document directory
        doc_dir = self.storage_dir / document_id
        doc_dir.mkdir(exist_ok=True)
        
        # Get original file extension
        source_file = Path(source_path)
        extension = source_file.suffix
        
        # Create versioned filename
        versioned_filename = f"{document_id}_v{version}{extension}"
        versioned_path = doc_dir / versioned_filename
        
        # Copy file
        shutil.copy2(source_path, versioned_path)
        
        logger.debug(f"Created versioned file: {versioned_path}")
        return str(versioned_path)
    
    def _cleanup_old_versions(self, document_id: str):
        """Clean up old versions beyond the retention limit"""
        
        versions = self.version_registry.get(document_id, [])
        
        if len(versions) > self.max_versions_per_document:
            # Sort by timestamp, keep the newest ones
            versions.sort(key=lambda x: x['timestamp'])
            
            versions_to_remove = versions[:-self.max_versions_per_document]
            
            for version_data in versions_to_remove:
                try:
                    # Delete physical file
                    file_path = Path(version_data['file_path'])
                    if file_path.exists():
                        file_path.unlink()
                    
                    # Remove from registry
                    self.version_registry[document_id].remove(version_data)
                    
                    logger.debug(f"Cleaned up old version: {version_data['version']}")
                    
                except Exception as e:
                    logger.warning(f"Error cleaning up version {version_data['version']}: {e}")
    
    def _generate_operation_id(self) -> str:
        """Generate unique operation ID"""
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        return f"op_{timestamp}_{len(self.update_operations)}"
    
    def get_document_history(self, document_id: str) -> Dict[str, Any]:
        """Get complete history for a document"""
        
        versions = self._get_document_versions(document_id)
        
        if not versions:
            return {'document_id': document_id, 'versions': [], 'current_version': None}
        
        current_version = self._get_current_version(document_id)
        
        # Get operations for this document
        operations = [
            op for op in self.update_operations 
            if self._generate_document_id(DocumentInfo(**op['document_info'])) == document_id
        ]
        
        return {
            'document_id': document_id,
            'versions': versions,
            'current_version': current_version,
            'operations': operations,
            'total_versions': len(versions)
        }
    
    def rollback_to_version(self, document_id: str, target_version: str) -> bool:
        """Rollback a document to a specific version"""
        
        try:
            versions = self._get_document_versions(document_id)
            target_version_data = None
            
            # Find target version
            for version in versions:
                if version['version'] == target_version:
                    target_version_data = version
                    break
            
            if not target_version_data:
                logger.error(f"Target version {target_version} not found for document {document_id}")
                return False
            
            # Mark all versions as not current
            for version in versions:
                version['is_current'] = False
            
            # Mark target version as current
            target_version_data['is_current'] = True
            
            # Update registry
            self._save_version_registry()
            
            logger.info(f"Rolled back document {document_id} to version {target_version}")
            return True
            
        except Exception as e:
            logger.error(f"Error rolling back document {document_id}: {e}")
            return False
    
    def get_version_statistics(self) -> Dict[str, Any]:
        """Get comprehensive version management statistics"""
        
        total_documents = len(self.version_registry)
        total_versions = sum(len(versions) for versions in self.version_registry.values())
        
        # Count by criterion
        criterion_counts = defaultdict(int)
        for document_id, versions in self.version_registry.items():
            current_version = self._get_current_version(document_id)
            if current_version:
                criterion = current_version.get('metadata', {}).get('criterion', 'unknown')
                criterion_counts[criterion] += 1
        
        # Recent activity
        recent_cutoff = datetime.now() - timedelta(days=7)
        recent_operations = [
            op for op in self.update_operations
            if datetime.fromisoformat(op['timestamp']) > recent_cutoff
        ]
        
        return {
            'total_documents': total_documents,
            'total_versions': total_versions,
            'average_versions_per_document': total_versions / total_documents if total_documents > 0 else 0,
            'criterion_distribution': dict(criterion_counts),
            'recent_operations_7_days': len(recent_operations),
            'storage_directory': str(self.storage_dir),
            'retention_policy': {
                'max_versions_per_document': self.max_versions_per_document
            }
        }
    
    def _build_document_id_mapping(self) -> Dict[str, str]:
        """Build mapping from document URLs to document IDs""" 
        mapping = {}
        
        for document_id, versions in self.version_registry.items():
            for version in versions:
                doc_url = version.get('metadata', {}).get('url')
                if doc_url:
                    mapping[doc_url] = document_id
        
        return mapping
    
    def _load_version_registry(self) -> Dict[str, List[Dict[str, Any]]]:
        """Load version registry from file"""
        
        registry_file = self.storage_dir / "version_registry.json"
        
        if registry_file.exists():
            try:
                with open(registry_file, 'r') as f:
                    return json.load(f)
            except Exception as e:
                logger.warning(f"Error loading version registry: {e}")
        
        return {}
    
    def _save_version_registry(self):
        """Save version registry to file"""
        
        registry_file = self.storage_dir / "version_registry.json"
        
        try:
            with open(registry_file, 'w') as f:
                json.dump(self.version_registry, f, indent=2)
        except Exception as e:
            logger.error(f"Error saving version registry: {e}")
    
    def _load_update_operations(self) -> List[Dict[str, Any]]:
        """Load update operations from file"""
        
        operations_file = self.storage_dir / "update_operations.json"
        
        if operations_file.exists():
            try:
                with open(operations_file, 'r') as f:
                    return json.load(f)
            except Exception as e:
                logger.warning(f"Error loading update operations: {e}")
        
        return []
    
    def _save_update_operations(self):
        """Save update operations to file"""
        
        operations_file = self.storage_dir / "update_operations.json"
        
        # Keep only last 500 operations
        if len(self.update_operations) > 500:
            self.update_operations = self.update_operations[-500:]
        
        try:
            with open(operations_file, 'w') as f:
                json.dump(self.update_operations, f, indent=2)
        except Exception as e:
            logger.error(f"Error saving update operations: {e}")