"""
Main Document Ingestion Pipeline for NAAC Compliance Intelligence System
Orchestrates PDF loading, chunking, and vector store ingestion
"""

import hashlib
import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Protocol

from .chunker import DocumentChunker, TextChunk
from .pdf_loader import PDFLoader


class VectorStore(Protocol):
    def add_naac_documents(self, documents: List[str], metadatas: List[Dict[str, Any]]): ...
    def add_mvsr_documents(self, documents: List[str], metadatas: List[Dict[str, Any]]): ...
    def get_collection_stats(self) -> Dict[str, Any]: ...
    def update_naac_version(self, old_version: str, new_version: str): ...


logger = logging.getLogger(__name__)


class DocumentIngestionPipeline:
    """
    Complete document ingestion pipeline that handles:
    1. PDF loading and text extraction
    2. Intelligent document chunking
    3. Vector store ingestion with metadata
    4. Duplicate detection and version management
    """

    def __init__(
        self,
        vector_store: VectorStore,
        chunk_size: int = 512,
        chunk_overlap: int = 50,
    ):
        """
        Initialize ingestion pipeline

        Args:
            vector_store: Vector store instance (Supabase pgvector)
            chunk_size: Target size for text chunks
            chunk_overlap: Overlap between consecutive chunks
        """
        self.vector_store = vector_store
        self.pdf_loader = PDFLoader()
        self.chunker = DocumentChunker(
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap,
        )

        # Track ingested documents to avoid duplicates
        self.ingestion_log = self._load_ingestion_log()

    def ingest_naac_documents(
        self,
        directory_path: str,
        version: str = "2025",
        force_reingest: bool = False,
    ) -> Dict[str, Any]:
        """
        Ingest NAAC requirement documents from directory

        Args:
            directory_path: Path to directory containing NAAC PDFs
            version: NAAC version identifier
            force_reingest: Whether to reingest already processed files

        Returns:
            Ingestion results and statistics
        """
        logger.info("Starting NAAC document ingestion from %s", directory_path)

        directory = Path(directory_path)
        if not directory.exists():
            raise FileNotFoundError(f"NAAC directory not found: {directory}")

        document_results: List[Dict[str, Any]] = []
        chunk_documents: List[str] = []
        chunk_metadatas: List[Dict[str, Any]] = []

        # Process criterion subdirectories
        for criterion_dir in directory.iterdir():
            if not (criterion_dir.is_dir() and criterion_dir.name.startswith("criterion_")):
                continue

            criterion_num = criterion_dir.name.split("_")[1]
            logger.info("Processing NAAC Criterion %s documents", criterion_num)

            for pdf_file in criterion_dir.glob("*.pdf"):
                try:
                    if not force_reingest and self._is_document_ingested(pdf_file, "naac_requirement"):
                        logger.info("Skipping already ingested file: %s", pdf_file.name)
                        continue

                    text, metadata = self.pdf_loader.load_pdf(str(pdf_file), "naac_requirement")
                    metadata.criterion = criterion_num
                    metadata.version = version

                    chunks = self._chunk_with_fallback(text, metadata.__dict__.copy())
                    if not chunks:
                        raise ValueError("No text chunks generated")

                    documents, metadatas = self._prepare_chunk_rows(chunks, metadata.__dict__.copy())
                    chunk_documents.extend(documents)
                    chunk_metadatas.extend(metadatas)

                    self._log_ingestion(pdf_file, "naac_requirement", len(chunks))
                    document_results.append(
                        {
                            "file": pdf_file.name,
                            "criterion": criterion_num,
                            "chunks": len(chunks),
                            "status": "success",
                        }
                    )
                except Exception as e:
                    logger.error("Failed to ingest NAAC document %s: %s", pdf_file.name, e)
                    document_results.append(
                        {
                            "file": pdf_file.name,
                            "criterion": criterion_num,
                            "chunks": 0,
                            "status": "failed",
                            "error": str(e),
                        }
                    )

        # Process files directly in NAAC root directory
        for pdf_file in directory.glob("*.pdf"):
            try:
                if not force_reingest and self._is_document_ingested(pdf_file, "naac_requirement"):
                    continue

                text, metadata = self.pdf_loader.load_pdf(str(pdf_file), "naac_requirement")
                metadata.version = version
                chunks = self._chunk_with_fallback(text, metadata.__dict__.copy())
                if not chunks:
                    raise ValueError("No text chunks generated")

                documents, metadatas = self._prepare_chunk_rows(chunks, metadata.__dict__.copy())
                chunk_documents.extend(documents)
                chunk_metadatas.extend(metadatas)

                self._log_ingestion(pdf_file, "naac_requirement", len(chunks))
                document_results.append(
                    {
                        "file": pdf_file.name,
                        "criterion": metadata.criterion or "general",
                        "chunks": len(chunks),
                        "status": "success",
                    }
                )
            except Exception as e:
                logger.error("Failed to ingest NAAC document %s: %s", pdf_file.name, e)
                document_results.append(
                    {
                        "file": pdf_file.name,
                        "criterion": "unknown",
                        "chunks": 0,
                        "status": "failed",
                        "error": str(e),
                    }
                )

        total_chunks_written = 0
        if chunk_documents:
            self.vector_store.add_naac_documents(chunk_documents, chunk_metadatas)
            total_chunks_written = len(chunk_documents)

        results = {
            "document_type": "naac_requirements",
            "total_files_processed": len(document_results),
            "successful_files": len([r for r in document_results if r["status"] == "success"]),
            "total_chunks_written": total_chunks_written,
            "version": version,
            "ingestion_timestamp": datetime.now().isoformat(),
            "detailed_results": document_results,
        }

        logger.info(
            "NAAC ingestion completed: %s files chunked into %s row(s)",
            results["successful_files"],
            total_chunks_written,
        )
        return results

    def ingest_mvsr_documents(
        self,
        directory_path: str,
        force_reingest: bool = False,
    ) -> Dict[str, Any]:
        """
        Ingest MVSR evidence documents from directory

        Args:
            directory_path: Path to directory containing MVSR evidence PDFs
            force_reingest: Whether to reingest already processed files

        Returns:
            Ingestion results and statistics
        """
        logger.info("Starting MVSR document ingestion from %s", directory_path)

        directory = Path(directory_path)
        if not directory.exists():
            raise FileNotFoundError(f"MVSR directory not found: {directory}")

        document_results: List[Dict[str, Any]] = []
        chunk_documents: List[str] = []
        chunk_metadatas: List[Dict[str, Any]] = []

        # Process category subdirectories
        for category_dir in directory.iterdir():
            if not category_dir.is_dir():
                continue

            category = category_dir.name
            logger.info("Processing MVSR %s documents", category)

            for pdf_file in category_dir.glob("*.pdf"):
                try:
                    if not force_reingest and self._is_document_ingested(pdf_file, "mvsr_evidence"):
                        logger.info("Skipping already ingested file: %s", pdf_file.name)
                        continue

                    text, metadata = self.pdf_loader.load_pdf(str(pdf_file), "mvsr_evidence")
                    metadata.category = category
                    chunks = self._chunk_with_fallback(text, metadata.__dict__.copy())
                    if not chunks:
                        raise ValueError("No text chunks generated")

                    documents, metadatas = self._prepare_chunk_rows(chunks, metadata.__dict__.copy())
                    chunk_documents.extend(documents)
                    chunk_metadatas.extend(metadatas)

                    self._log_ingestion(pdf_file, "mvsr_evidence", len(chunks))
                    document_results.append(
                        {
                            "file": pdf_file.name,
                            "category": category,
                            "mapped_criterion": metadata.criterion,
                            "chunks": len(chunks),
                            "status": "success",
                        }
                    )
                except Exception as e:
                    logger.error("Failed to ingest MVSR document %s: %s", pdf_file.name, e)
                    document_results.append(
                        {
                            "file": pdf_file.name,
                            "category": category,
                            "chunks": 0,
                            "status": "failed",
                            "error": str(e),
                        }
                    )

        # Process files directly in MVSR root directory
        for pdf_file in directory.glob("*.pdf"):
            try:
                if not force_reingest and self._is_document_ingested(pdf_file, "mvsr_evidence"):
                    continue

                text, metadata = self.pdf_loader.load_pdf(str(pdf_file), "mvsr_evidence")
                chunks = self._chunk_with_fallback(text, metadata.__dict__.copy())
                if not chunks:
                    raise ValueError("No text chunks generated")

                documents, metadatas = self._prepare_chunk_rows(chunks, metadata.__dict__.copy())
                chunk_documents.extend(documents)
                chunk_metadatas.extend(metadatas)

                self._log_ingestion(pdf_file, "mvsr_evidence", len(chunks))
                document_results.append(
                    {
                        "file": pdf_file.name,
                        "category": metadata.category or "general",
                        "mapped_criterion": metadata.criterion,
                        "chunks": len(chunks),
                        "status": "success",
                    }
                )
            except Exception as e:
                logger.error("Failed to ingest MVSR document %s: %s", pdf_file.name, e)
                document_results.append(
                    {
                        "file": pdf_file.name,
                        "category": "unknown",
                        "chunks": 0,
                        "status": "failed",
                        "error": str(e),
                    }
                )

        total_chunks_written = 0
        if chunk_documents:
            self.vector_store.add_mvsr_documents(chunk_documents, chunk_metadatas)
            total_chunks_written = len(chunk_documents)

        results = {
            "document_type": "mvsr_evidence",
            "total_files_processed": len(document_results),
            "successful_files": len([r for r in document_results if r["status"] == "success"]),
            "total_chunks_written": total_chunks_written,
            "ingestion_timestamp": datetime.now().isoformat(),
            "detailed_results": document_results,
        }

        logger.info(
            "MVSR ingestion completed: %s files chunked into %s row(s)",
            results["successful_files"],
            total_chunks_written,
        )
        return results

    def ingest_single_document(
        self,
        file_path: str,
        document_type: str,
        additional_metadata: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Ingest a single document

        Args:
            file_path: Path to PDF file
            document_type: 'naac_requirement' or 'mvsr_evidence'
            additional_metadata: Additional metadata to include

        Returns:
            Ingestion results
        """
        logger.info("Ingesting single document: %s", file_path)

        path_obj = Path(file_path)
        if not path_obj.exists():
            raise FileNotFoundError(f"Document not found: {path_obj}")

        try:
            text, metadata = self.pdf_loader.load_pdf(str(path_obj), document_type)

            if additional_metadata:
                for key, value in additional_metadata.items():
                    setattr(metadata, key, value)

            chunks = self._chunk_with_fallback(text, metadata.__dict__.copy())
            if not chunks:
                return {
                    "file": path_obj.name,
                    "status": "failed",
                    "error": "No text extracted from document",
                }

            documents, metadatas = self._prepare_chunk_rows(chunks, metadata.__dict__.copy())

            if document_type == "naac_requirement":
                self.vector_store.add_naac_documents(documents, metadatas)
            elif document_type == "mvsr_evidence":
                self.vector_store.add_mvsr_documents(documents, metadatas)
            else:
                raise ValueError(f"Invalid document type: {document_type}")

            self._log_ingestion(path_obj, document_type, len(chunks))
            result = {
                "file": path_obj.name,
                "document_type": document_type,
                "chunks_written": len(chunks),
                "status": "success",
                "ingestion_timestamp": datetime.now().isoformat(),
                "metadata": metadata.__dict__,
            }

            logger.info("Successfully ingested %s as %s chunk rows", path_obj.name, len(chunks))
            return result
        except Exception as e:
            logger.error("Failed to ingest document %s: %s", path_obj.name, e)
            return {
                "file": path_obj.name,
                "status": "failed",
                "error": str(e),
            }

    def get_ingestion_statistics(self) -> Dict[str, Any]:
        """Get comprehensive ingestion statistics"""
        vector_stats = self.vector_store.get_collection_stats()

        naac_files = len(
            [entry for entry in self.ingestion_log if entry.get("document_type") == "naac_requirement"]
        )
        mvsr_files = len(
            [entry for entry in self.ingestion_log if entry.get("document_type") == "mvsr_evidence"]
        )

        return {
            "vector_store_stats": vector_stats,
            "ingestion_history": {
                "naac_files_ingested": naac_files,
                "mvsr_files_ingested": mvsr_files,
                "total_files_ingested": len(self.ingestion_log),
                "last_ingestion": self.ingestion_log[-1]["timestamp"] if self.ingestion_log else None,
            },
        }

    def _chunk_with_fallback(self, text: str, base_metadata: Dict[str, Any]) -> List[TextChunk]:
        """Chunk text and fallback to one cleaned chunk when structural chunking yields none."""
        chunks = self.chunker.chunk_document(text, base_metadata)
        if chunks:
            return chunks

        cleaned_text = " ".join((text or "").split())
        if not cleaned_text:
            return []

        total_pages = int(base_metadata.get("total_pages", 1) or 1)
        return [
            TextChunk(
                text=cleaned_text,
                chunk_index=0,
                start_page=1,
                end_page=total_pages,
                chunk_type="content",
                metadata=base_metadata.copy(),
            )
        ]

    def _prepare_chunk_rows(
        self,
        chunks: List[TextChunk],
        base_metadata: Dict[str, Any],
    ) -> tuple[List[str], List[Dict[str, Any]]]:
        """Convert chunk objects into vector-store row payloads."""
        documents: List[str] = []
        metadatas: List[Dict[str, Any]] = []

        for chunk in chunks:
            documents.append(chunk.text)
            metadatas.append(self._build_chunk_metadata(base_metadata, chunk))

        return documents, metadatas

    def _build_chunk_metadata(self, base_metadata: Dict[str, Any], chunk: TextChunk) -> Dict[str, Any]:
        """Merge base document metadata with chunk fields."""
        merged = base_metadata.copy()
        merged.update(chunk.metadata or {})
        merged.update(
            {
                "chunk_index": chunk.chunk_index,
                "start_page": chunk.start_page,
                "end_page": chunk.end_page,
                "chunk_type": chunk.chunk_type,
                "storage_mode": "chunk_row",
                "source_file": merged.get("source_file") or merged.get("file_name", ""),
            }
        )
        return merged

    def _is_document_ingested(self, file_path: Path, document_type: str) -> bool:
        """Check if document was already ingested."""
        file_hash = self._calculate_file_hash(file_path)
        for entry in self.ingestion_log:
            if entry.get("file_hash") == file_hash and entry.get("document_type") == document_type:
                return True
        return False

    def _log_ingestion(self, file_path: Path, document_type: str, chunk_count: int):
        """Log successful document ingestion."""
        entry = {
            "file_path": str(file_path),
            "file_name": file_path.name,
            "file_hash": self._calculate_file_hash(file_path),
            "document_type": document_type,
            "chunk_count": chunk_count,
            "timestamp": datetime.now().isoformat(),
        }
        self.ingestion_log.append(entry)
        self._save_ingestion_log()

    def _calculate_file_hash(self, file_path: Path) -> str:
        """Calculate SHA-256 hash of file."""
        hash_sha256 = hashlib.sha256()
        with open(file_path, "rb") as f:
            for chunk in iter(lambda: f.read(4096), b""):
                hash_sha256.update(chunk)
        return hash_sha256.hexdigest()[:16]

    def _load_ingestion_log(self) -> List[Dict[str, Any]]:
        """Load ingestion log from file."""
        log_file = Path("ingestion_log.json")
        if log_file.exists():
            try:
                with open(log_file, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception as e:
                logger.warning("Could not load ingestion log: %s", e)
        return []

    def _save_ingestion_log(self):
        """Save ingestion log to file."""
        log_file = Path("ingestion_log.json")
        try:
            with open(log_file, "w", encoding="utf-8") as f:
                json.dump(self.ingestion_log, f, indent=2)
        except Exception as e:
            logger.error("Could not save ingestion log: %s", e)

    def clear_ingestion_log(self):
        """Clear the ingestion log (use with caution)."""
        self.ingestion_log = []
        self._save_ingestion_log()
        logger.info("Ingestion log cleared")
