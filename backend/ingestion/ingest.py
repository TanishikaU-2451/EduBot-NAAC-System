"""
Main Document Ingestion Pipeline for NAAC Compliance Intelligence System
Orchestrates PDF loading, chunking, and vector store ingestion
"""

import hashlib
import json
import re
import logging
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Protocol

from ..debug.trace_logger import get_pipeline_trace_logger
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
        large_document_page_threshold: int = 120,
        large_document_chunk_size: Optional[int] = None,
        large_document_chunk_overlap: Optional[int] = None,
        min_chunk_length: int = 180,
        pdf_extraction_strategy: str = "auto",
        pdf_extract_tables: bool = False,
    ):
        """
        Initialize ingestion pipeline

        Args:
            vector_store: Vector store instance (Supabase pgvector)
            chunk_size: Target size for text chunks
            chunk_overlap: Overlap between consecutive chunks
        """
        self.vector_store = vector_store
        self.large_document_page_threshold = max(int(large_document_page_threshold or 120), 1)
        self.min_chunk_length = max(int(min_chunk_length or 180), 50)

        self.pdf_loader = PDFLoader(
            preferred_extractor=pdf_extraction_strategy,
            extract_tables=pdf_extract_tables,
            large_document_page_threshold=self.large_document_page_threshold,
        )
        self.chunker = DocumentChunker(
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap,
        )
        self.large_document_chunker = DocumentChunker(
            chunk_size=max(int(large_document_chunk_size or max(chunk_size, 1800)), chunk_size),
            chunk_overlap=max(
                0,
                min(
                    int(large_document_chunk_overlap or min(chunk_overlap, 120)),
                    max(int(large_document_chunk_size or max(chunk_size, 1800)) - 1, 0),
                ),
            ),
        )
        self.trace_logger = get_pipeline_trace_logger()

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

        trace_id = self.trace_logger.create_trace_id("ingest", path_obj.stem)
        logger.info("Ingestion trace id: %s", trace_id)
        self.trace_logger.write_json(
            trace_id,
            "00_ingest_request.json",
            {
                "timestamp": datetime.now().isoformat(),
                "file_path": str(path_obj),
                "document_type": document_type,
                "additional_metadata": additional_metadata or {},
                "chunker_config": {
                    "default_chunk_size": self.chunker.chunk_size,
                    "default_chunk_overlap": self.chunker.chunk_overlap,
                    "large_document_page_threshold": self.large_document_page_threshold,
                    "large_document_chunk_size": self.large_document_chunker.chunk_size,
                    "large_document_chunk_overlap": self.large_document_chunker.chunk_overlap,
                    "min_chunk_length": self.min_chunk_length,
                },
            },
        )

        try:
            text, metadata = self.pdf_loader.load_pdf(str(path_obj), document_type)

            if additional_metadata:
                for key, value in additional_metadata.items():
                    setattr(metadata, key, value)

            metadata_dict = metadata.__dict__.copy()
            total_pages = int(metadata_dict.get("total_pages", 1) or 1)
            chunker_name = (
                "large_document_chunker"
                if total_pages >= self.large_document_page_threshold
                else "default_chunker"
            )
            self.trace_logger.write_json(
                trace_id,
                "01_extraction_summary.json",
                {
                    "file": path_obj.name,
                    "document_type": document_type,
                    "text_length": len(text or ""),
                    "total_pages": total_pages,
                    "chunker_selected": chunker_name,
                    "metadata": metadata_dict,
                },
            )
            self.trace_logger.write_text(trace_id, "01_extracted_text.txt", text or "")

            chunks = self._chunk_with_fallback(text, metadata_dict)
            if not chunks:
                self.trace_logger.write_json(
                    trace_id,
                    "02_chunk_summary.json",
                    {
                        "chunks_generated": 0,
                        "message": "No chunks were produced from extracted text.",
                    },
                )
                return {
                    "file": path_obj.name,
                    "status": "failed",
                    "error": "No text extracted from document",
                }

            self.trace_logger.write_json(
                trace_id,
                "02_chunk_summary.json",
                self._summarize_chunks(chunks),
            )
            self.trace_logger.write_json(
                trace_id,
                "02_chunks.json",
                self._serialize_chunks(chunks),
            )

            documents, metadatas = self._prepare_chunk_rows(chunks, metadata_dict)
            self.trace_logger.write_json(
                trace_id,
                "03_vector_rows.json",
                {
                    "rows_written": len(documents),
                    "documents": documents,
                    "metadatas": metadatas,
                },
            )
            if not documents:
                self.trace_logger.write_json(
                    trace_id,
                    "99_ingest_result.json",
                    {
                        "file": path_obj.name,
                        "status": "failed",
                        "error": "No vector rows remained after chunk cleaning and deduplication.",
                        "debug_trace_id": trace_id,
                    },
                )
                return {
                    "file": path_obj.name,
                    "status": "failed",
                    "error": "No vector rows remained after chunk cleaning and deduplication.",
                    "debug_trace_id": trace_id,
                }

            logger.info(
                "[DB-WRITE] About to write %d chunks for '%s' (type=%s) to vector store",
                len(documents),
                path_obj.name,
                document_type,
            )

            if document_type == "naac_requirement":
                self.vector_store.add_naac_documents(documents, metadatas)
            elif document_type == "mvsr_evidence":
                self.vector_store.add_mvsr_documents(documents, metadatas)
            else:
                raise ValueError(f"Invalid document type: {document_type}")

            # Confirm with stats after write
            try:
                stats = self.vector_store.get_collection_stats()
                logger.info(
                    "[DB-WRITE] ✓ Write complete. Vector store now has %s NAAC docs, %s MVSR docs.",
                    stats.get("naac_requirements_count", "?"),
                    stats.get("mvsr_evidence_count", "?"),
                )
            except Exception as stats_err:
                logger.warning("[DB-WRITE] Could not fetch post-write stats: %s", stats_err)

            self._log_ingestion(path_obj, document_type, len(documents))
            result = {
                "file": path_obj.name,
                "document_type": document_type,
                "chunks_generated": len(chunks),
                "chunks_written": len(documents),
                "status": "success",
                "ingestion_timestamp": datetime.now().isoformat(),
                "metadata": metadata_dict,
                "debug_trace_id": trace_id,
            }
            self.trace_logger.write_json(trace_id, "99_ingest_result.json", result)

            logger.info("Successfully ingested %s as %s chunk rows", path_obj.name, len(documents))
            return result
        except Exception as e:
            logger.error("Failed to ingest document %s: %s", path_obj.name, e, exc_info=True)
            self.trace_logger.write_error(
                trace_id,
                str(e),
                stage="ingest_single_document",
                file=path_obj.name,
                document_type=document_type,
            )
            return {
                "file": path_obj.name,
                "status": "failed",
                "error": str(e),
                "debug_trace_id": trace_id,
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
        total_pages = int(base_metadata.get("total_pages", 1) or 1)
        chunker = self.large_document_chunker if total_pages >= self.large_document_page_threshold else self.chunker
        chunks = chunker.chunk_document(text, base_metadata)
        if chunks:
            return chunks

        cleaned_text = " ".join((text or "").split())
        if not cleaned_text:
            return []

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
        seen_documents = set()

        for chunk in chunks:
            cleaned_text = self._clean_chunk_text(chunk.text)
            if len(cleaned_text) < self.min_chunk_length:
                continue
            if cleaned_text in seen_documents:
                continue

            seen_documents.add(cleaned_text)
            documents.append(cleaned_text)

            metadata = self._build_chunk_metadata(base_metadata, chunk)
            metadata["chunk_length"] = len(cleaned_text)
            metadatas.append(metadata)

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
        merged["section_header"] = self._derive_section_header(chunk, merged)
        return merged

    def _serialize_chunks(self, chunks: List[TextChunk]) -> List[Dict[str, Any]]:
        """Convert chunk objects into debug-friendly dictionaries."""
        serialized = []
        for chunk in chunks:
            serialized.append(
                {
                    "chunk_index": chunk.chunk_index,
                    "chunk_type": chunk.chunk_type,
                    "start_page": chunk.start_page,
                    "end_page": chunk.end_page,
                    "text_length": len(chunk.text or ""),
                    "text_preview": (chunk.text or "")[:500],
                    "text": chunk.text or "",
                    "metadata": chunk.metadata or {},
                }
            )
        return serialized

    def _summarize_chunks(self, chunks: List[TextChunk]) -> Dict[str, Any]:
        """Build a compact chunking summary for trace inspection."""
        if not chunks:
            return {"chunks_generated": 0}

        stats = self.chunker.get_chunk_statistics(chunks)
        stats["chunks_generated"] = len(chunks)
        stats["sample_headers"] = [
            self._derive_section_header(chunk, chunk.metadata or {})
            for chunk in chunks[:5]
        ]
        return stats

    def _clean_chunk_text(self, text: str) -> str:
        """Remove page markers and noisy whitespace before embedding."""
        cleaned = text or ""
        cleaned = re.sub(r"---\s*Page\s+\d+\s*---", " ", cleaned)
        cleaned = re.sub(r"---\s*Table\s+\d+\s+on\s+Page\s+\d+\s*---", " ", cleaned)
        cleaned = cleaned.replace("\uf0b7", " ")
        cleaned = cleaned.replace("â€¢", " ")
        cleaned = cleaned.replace("Â·", " ")
        cleaned = cleaned.replace("\u2022", " ")
        cleaned = " ".join(cleaned.split())
        return cleaned.strip()

    def _derive_section_header(self, chunk: TextChunk, metadata: Dict[str, Any]) -> str:
        """Build a non-empty section header required by the database schema."""
        existing = str(metadata.get("section_header", "") or "").strip()
        if existing:
            return existing[:200]

        chunk_lines = [line.strip() for line in (chunk.text or "").splitlines()]
        for line in chunk_lines:
            if not line:
                continue
            if re.match(r"^---\s*(?:Page|Table)\b", line, re.IGNORECASE):
                continue
            if len(line) < 3:
                continue
            compact = re.sub(r"\s+", " ", line).strip(" -:|")
            if compact:
                return compact[:200]

        document_title = str(metadata.get("document_title", "") or "").strip()
        if document_title:
            return document_title[:200]

        source_file = str(metadata.get("source_file") or metadata.get("file_name") or "").strip()
        if source_file:
            return Path(source_file).stem[:200]

        return f"{chunk.chunk_type.title()} section p{chunk.start_page}-{chunk.end_page}"

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
