"""
Main Document Ingestion Pipeline for NAAC Compliance Intelligence System
Orchestrates PDF loading, chunking, and vector store ingestion
"""

import logging
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple
import json
import hashlib
from datetime import datetime

from .pdf_loader import PDFLoader, DocumentMetadata
from .chunker import DocumentChunker, TextChunk
from ..db.chroma_store import ChromaVectorStore

logger = logging.getLogger(__name__)

class DocumentIngestionPipeline:
    """
    Complete document ingestion pipeline that handles:
    1. PDF loading and text extraction
    2. Intelligent document chunking
    3. Vector store ingestion with metadata
    4. Duplicate detection and version management
    """
    
    def __init__(self, 
                 chroma_store: ChromaVectorStore,
                 chunk_size: int = 512,
                 chunk_overlap: int = 50):
        """
        Initialize ingestion pipeline
        
        Args:
            chroma_store: ChromaDB vector store instance
            chunk_size: Target size for text chunks
            chunk_overlap: Overlap between consecutive chunks
        """
        self.chroma_store = chroma_store
        self.pdf_loader = PDFLoader()
        self.chunker = DocumentChunker(
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap
        )
        
        # Track ingested documents to avoid duplicates
        self.ingestion_log = self._load_ingestion_log()
    
    def ingest_naac_documents(self, 
                            directory_path: str,
                            version: str = "2025",
                            force_reingest: bool = False) -> Dict[str, Any]:
        """
        Ingest NAAC requirement documents from directory
        
        Args:
            directory_path: Path to directory containing NAAC PDFs
            version: NAAC version identifier
            force_reingest: Whether to reingest already processed files
            
        Returns:
            Ingestion results and statistics
        """
        logger.info(f"Starting NAAC document ingestion from {directory_path}")
        
        directory = Path(directory_path)
        if not directory.exists():
            raise FileNotFoundError(f"NAAC directory not found: {directory}")
        
        # Load all PDFs from directory and subdirectories
        document_results = []
        total_chunks = 0
        
        # Process criterion subdirectories
        for criterion_dir in directory.iterdir():
            if criterion_dir.is_dir() and criterion_dir.name.startswith('criterion_'):
                criterion_num = criterion_dir.name.split('_')[1]
                logger.info(f"Processing NAAC Criterion {criterion_num} documents")
                
                pdf_files = list(criterion_dir.glob("*.pdf"))
                for pdf_file in pdf_files:
                    try:
                        # Check if already ingested
                        if not force_reingest and self._is_document_ingested(pdf_file, "naac_requirement"):
                            logger.info(f"Skipping already ingested file: {pdf_file.name}")
                            continue
                        
                        # Load and process PDF
                        text, metadata = self.pdf_loader.load_pdf(str(pdf_file), "naac_requirement")
                        
                        # Override criterion from directory structure
                        metadata.criterion = criterion_num
                        metadata.version = version
                        
                        # Chunk the document
                        chunks = self.chunker.chunk_document(text, metadata.__dict__)
                        
                        if chunks:
                            # Prepare for vector store
                            documents, metadatas = self.chunker.prepare_for_vectorstore(chunks)
                            
                            # Add to ChromaDB
                            self.chroma_store.add_naac_documents(documents, metadatas)
                            
                            # Log successful ingestion
                            self._log_ingestion(pdf_file, "naac_requirement", len(chunks))
                            
                            document_results.append({
                                'file': pdf_file.name,
                                'criterion': criterion_num,
                                'chunks': len(chunks),
                                'status': 'success'
                            })
                            total_chunks += len(chunks)
                        
                    except Exception as e:
                        logger.error(f"Failed to ingest NAAC document {pdf_file.name}: {e}")
                        document_results.append({
                            'file': pdf_file.name,
                            'criterion': criterion_num,
                            'chunks': 0,
                            'status': 'failed',
                            'error': str(e)
                        })
        
        # Also process files directly in the main naac_requirements directory
        main_pdf_files = list(directory.glob("*.pdf"))
        for pdf_file in main_pdf_files:
            try:
                if not force_reingest and self._is_document_ingested(pdf_file, "naac_requirement"):
                    continue
                
                text, metadata = self.pdf_loader.load_pdf(str(pdf_file), "naac_requirement")
                metadata.version = version
                
                chunks = self.chunker.chunk_document(text, metadata.__dict__)
                
                if chunks:
                    documents, metadatas = self.chunker.prepare_for_vectorstore(chunks)
                    self.chroma_store.add_naac_documents(documents, metadatas)
                    self._log_ingestion(pdf_file, "naac_requirement", len(chunks))
                    
                    document_results.append({
                        'file': pdf_file.name,
                        'criterion': metadata.criterion or 'general',
                        'chunks': len(chunks),
                        'status': 'success'
                    })
                    total_chunks += len(chunks)
                    
            except Exception as e:
                logger.error(f"Failed to ingest NAAC document {pdf_file.name}: {e}")
                
        
        results = {
            'document_type': 'naac_requirements',
            'total_files_processed': len(document_results),
            'successful_files': len([r for r in document_results if r['status'] == 'success']),
            'total_chunks_created': total_chunks,
            'version': version,
            'ingestion_timestamp': datetime.now().isoformat(),
            'detailed_results': document_results
        }
        
        logger.info(f"NAAC ingestion completed: {results['successful_files']} files, {total_chunks} chunks")
        return results
    
    def ingest_mvsr_documents(self, 
                            directory_path: str,
                            force_reingest: bool = False) -> Dict[str, Any]:
        """
        Ingest MVSR evidence documents from directory
        
        Args:
            directory_path: Path to directory containing MVSR evidence PDFs
            force_reingest: Whether to reingest already processed files
            
        Returns:
            Ingestion results and statistics
        """
        logger.info(f"Starting MVSR document ingestion from {directory_path}")
        
        directory = Path(directory_path)
        if not directory.exists():
            raise FileNotFoundError(f"MVSR directory not found: {directory}")
        
        document_results = []
        total_chunks = 0
        
        # Process category subdirectories
        for category_dir in directory.iterdir():
            if category_dir.is_dir():
                category = category_dir.name
                logger.info(f"Processing MVSR {category} documents")
                
                pdf_files = list(category_dir.glob("*.pdf"))
                for pdf_file in pdf_files:
                    try:
                        # Check if already ingested
                        if not force_reingest and self._is_document_ingested(pdf_file, "mvsr_evidence"):
                            logger.info(f"Skipping already ingested file: {pdf_file.name}")
                            continue
                        
                        # Load and process PDF
                        text, metadata = self.pdf_loader.load_pdf(str(pdf_file), "mvsr_evidence")
                        
                        # Override category from directory structure
                        metadata.category = category
                        
                        # Chunk the document
                        chunks = self.chunker.chunk_document(text, metadata.__dict__)
                        
                        if chunks:
                            # Prepare for vector store
                            documents, metadatas = self.chunker.prepare_for_vectorstore(chunks)
                            
                            # Add to ChromaDB
                            self.chroma_store.add_mvsr_documents(documents, metadatas)
                            
                            # Log successful ingestion
                            self._log_ingestion(pdf_file, "mvsr_evidence", len(chunks))
                            
                            document_results.append({
                                'file': pdf_file.name,
                                'category': category,
                                'mapped_criterion': metadata.criterion,
                                'chunks': len(chunks),
                                'status': 'success'
                            })
                            total_chunks += len(chunks)
                        
                    except Exception as e:
                        logger.error(f"Failed to ingest MVSR document {pdf_file.name}: {e}")
                        document_results.append({
                            'file': pdf_file.name,
                            'category': category,
                            'chunks': 0,
                            'status': 'failed',
                            'error': str(e)
                        })
        
        # Process files directly in the main mvsr_evidence directory
        main_pdf_files = list(directory.glob("*.pdf"))
        for pdf_file in main_pdf_files:
            try:
                if not force_reingest and self._is_document_ingested(pdf_file, "mvsr_evidence"):
                    continue
                
                text, metadata = self.pdf_loader.load_pdf(str(pdf_file), "mvsr_evidence")
                chunks = self.chunker.chunk_document(text, metadata.__dict__)
                
                if chunks:
                    documents, metadatas = self.chunker.prepare_for_vectorstore(chunks)
                    self.chroma_store.add_mvsr_documents(documents, metadatas)
                    self._log_ingestion(pdf_file, "mvsr_evidence", len(chunks))
                    
                    document_results.append({
                        'file': pdf_file.name,
                        'category': metadata.category or 'general',
                        'mapped_criterion': metadata.criterion,
                        'chunks': len(chunks),
                        'status': 'success'
                    })
                    total_chunks += len(chunks)
                    
            except Exception as e:
                logger.error(f"Failed to ingest MVSR document {pdf_file.name}: {e}")
        
        results = {
            'document_type': 'mvsr_evidence',
            'total_files_processed': len(document_results),
            'successful_files': len([r for r in document_results if r['status'] == 'success']),
            'total_chunks_created': total_chunks,
            'ingestion_timestamp': datetime.now().isoformat(),
            'detailed_results': document_results
        }
        
        logger.info(f"MVSR ingestion completed: {results['successful_files']} files, {total_chunks} chunks")
        return results
    
    def ingest_single_document(self, 
                             file_path: str, 
                             document_type: str,
                             additional_metadata: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        Ingest a single document
        
        Args:
            file_path: Path to PDF file
            document_type: 'naac_requirement' or 'mvsr_evidence'
            additional_metadata: Additional metadata to include
            
        Returns:
            Ingestion results
        """
        logger.info(f"Ingesting single document: {file_path}")
        
        file_path = Path(file_path)
        if not file_path.exists():
            raise FileNotFoundError(f"Document not found: {file_path}")
        
        try:
            # Load PDF
            text, metadata = self.pdf_loader.load_pdf(str(file_path), document_type)
            
            # Add additional metadata if provided
            if additional_metadata:
                for key, value in additional_metadata.items():
                    setattr(metadata, key, value)
            
            # Chunk document
            chunks = self.chunker.chunk_document(text, metadata.__dict__)
            
            if not chunks:
                return {
                    'file': file_path.name,
                    'status': 'failed',
                    'error': 'No chunks created from document'
                }
            
            # Prepare and store in vector database
            documents, metadatas = self.chunker.prepare_for_vectorstore(chunks)
            
            if document_type == "naac_requirement":
                self.chroma_store.add_naac_documents(documents, metadatas)
            elif document_type == "mvsr_evidence":
                self.chroma_store.add_mvsr_documents(documents, metadatas)
            else:
                raise ValueError(f"Invalid document type: {document_type}")
            
            # Log ingestion
            self._log_ingestion(file_path, document_type, len(chunks))
            
            result = {
                'file': file_path.name,
                'document_type': document_type,
                'chunks_created': len(chunks),
                'status': 'success',
                'ingestion_timestamp': datetime.now().isoformat(),
                'metadata': metadata.__dict__
            }
            
            logger.info(f"Successfully ingested {file_path.name}: {len(chunks)} chunks")
            return result
            
        except Exception as e:
            logger.error(f"Failed to ingest document {file_path.name}: {e}")
            return {
                'file': file_path.name,
                'status': 'failed',
                'error': str(e)
            }
    
    def get_ingestion_statistics(self) -> Dict[str, Any]:
        """Get comprehensive ingestion statistics"""
        chroma_stats = self.chroma_store.get_collection_stats()
        
        # Count by document type in ingestion log
        naac_files = len([entry for entry in self.ingestion_log 
                         if entry.get('document_type') == 'naac_requirement'])
        mvsr_files = len([entry for entry in self.ingestion_log 
                         if entry.get('document_type') == 'mvsr_evidence'])
        
        return {
            'vector_store_stats': chroma_stats,
            'ingestion_history': {
                'naac_files_ingested': naac_files,
                'mvsr_files_ingested': mvsr_files,
                'total_files_ingested': len(self.ingestion_log),
                'last_ingestion': self.ingestion_log[-1]['timestamp'] if self.ingestion_log else None
            }
        }
    
    def _is_document_ingested(self, file_path: Path, document_type: str) -> bool:
        """Check if document was already ingested"""
        file_hash = self._calculate_file_hash(file_path)
        
        for entry in self.ingestion_log:
            if (entry.get('file_hash') == file_hash and 
                entry.get('document_type') == document_type):
                return True
        return False
    
    def _log_ingestion(self, file_path: Path, document_type: str, chunk_count: int):
        """Log successful document ingestion"""
        entry = {
            'file_path': str(file_path),
            'file_name': file_path.name,
            'file_hash': self._calculate_file_hash(file_path),
            'document_type': document_type,
            'chunk_count': chunk_count,
            'timestamp': datetime.now().isoformat()
        }
        
        self.ingestion_log.append(entry)
        self._save_ingestion_log()
    
    def _calculate_file_hash(self, file_path: Path) -> str:
        """Calculate SHA-256 hash of file"""
        hash_sha256 = hashlib.sha256()
        
        with open(file_path, "rb") as f:
            for chunk in iter(lambda: f.read(4096), b""):
                hash_sha256.update(chunk)
        
        return hash_sha256.hexdigest()[:16]
    
    def _load_ingestion_log(self) -> List[Dict[str, Any]]:
        """Load ingestion log from file"""
        log_file = Path("ingestion_log.json")
        
        if log_file.exists():
            try:
                with open(log_file, 'r') as f:
                    return json.load(f)
            except Exception as e:
                logger.warning(f"Could not load ingestion log: {e}")
        
        return []
    
    def _save_ingestion_log(self):
        """Save ingestion log to file"""
        log_file = Path("ingestion_log.json")
        
        try:
            with open(log_file, 'w') as f:
                json.dump(self.ingestion_log, f, indent=2)
        except Exception as e:
            logger.error(f"Could not save ingestion log: {e}")
    
    def clear_ingestion_log(self):
        """Clear the ingestion log (use with caution)"""
        self.ingestion_log = []
        self._save_ingestion_log()
        logger.info("Ingestion log cleared")