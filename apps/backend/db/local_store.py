"""Simple in-memory vector store for local development.

Keeps NAAC and MVSR corpora in Python lists and performs cosine-similarity searches
using SentenceTransformer embeddings. This avoids heavyweight native dependencies
while providing enough functionality for demos and tests.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Sequence, Tuple

import numpy as np
from sentence_transformers import SentenceTransformer


@dataclass
class _VectorRecord:
    document: str
    metadata: Dict[str, Any]
    embedding: np.ndarray


class LocalVectorStore:
    """Minimal vector backend that lives entirely in memory."""

    def __init__(
        self,
        embedding_model: str = "all-MiniLM-L6-v2",
        embedding_device: str = "cpu",
        embedding_batch_size: int = 128,
    ) -> None:
        self.embedding_batch_size = max(int(embedding_batch_size or 128), 8)
        self.embedder = SentenceTransformer(embedding_model, device=embedding_device)
        self.naac_records: List[_VectorRecord] = []
        self.mvsr_records: List[_VectorRecord] = []

    # ------------------------------------------------------------------
    # Public ingestion helpers
    # ------------------------------------------------------------------
    def add_naac_documents(self, documents: Sequence[str], metadatas: Sequence[Dict[str, Any]]) -> None:
        self._append_records(self.naac_records, documents, metadatas, doc_type="requirement")

    def add_mvsr_documents(self, documents: Sequence[str], metadatas: Sequence[Dict[str, Any]]) -> None:
        self._append_records(self.mvsr_records, documents, metadatas, doc_type="evidence")

    # ------------------------------------------------------------------
    # Retrieval helpers
    # ------------------------------------------------------------------
    def query_naac_requirements(
        self,
        query_text: str,
        n_results: int = 5,
        criterion_filter: Optional[str] = None,
    ) -> Dict[str, Any]:
        return self._query_records(self.naac_records, query_text, n_results, ("criterion", criterion_filter))

    def query_mvsr_evidence(
        self,
        query_text: str,
        n_results: int = 5,
        category_filter: Optional[str] = None,
    ) -> Dict[str, Any]:
        return self._query_records(self.mvsr_records, query_text, n_results, ("category", category_filter))

    # ------------------------------------------------------------------
    # Diagnostics
    # ------------------------------------------------------------------
    def get_collection_stats(self) -> Dict[str, int]:
        return {
            "naac_requirements_count": len(self.naac_records),
            "mvsr_evidence_count": len(self.mvsr_records),
            "total_documents": len(self.naac_records) + len(self.mvsr_records),
        }

    def health_check(self) -> Dict[str, Any]:
        stats = self.get_collection_stats()
        stats.update({
            "ok": True,
            "backend": "local-memory",
        })
        return stats

    def consolidate_single_row_mode(self) -> None:
        """Compatibility shim for the Supabase backend interface."""
        return

    # ------------------------------------------------------------------
    # Internal utilities
    # ------------------------------------------------------------------
    def _append_records(
        self,
        store: List[_VectorRecord],
        documents: Sequence[str],
        metadatas: Sequence[Dict[str, Any]],
        doc_type: str,
    ) -> None:
        if not documents or not metadatas:
            return
        if len(documents) != len(metadatas):
            raise ValueError("Documents and metadata must have the same length")

        embeddings = self._encode(list(documents))
        for doc, metadata, embedding in zip(documents, metadatas, embeddings, strict=False):
            clean_meta = dict(metadata or {})
            clean_meta.setdefault("type", doc_type)
            store.append(_VectorRecord(document=doc, metadata=clean_meta, embedding=embedding))

    def _query_records(
        self,
        store: List[_VectorRecord],
        query_text: str,
        n_results: int,
        filter_pair: Tuple[str, Optional[str]],
    ) -> Dict[str, Any]:
        if not store:
            return {"documents": [], "metadatas": [], "distances": []}

        filter_key, filter_value = filter_pair
        candidates = (
            record
            for record in store
            if not filter_value or record.metadata.get(filter_key) == filter_value
        )
        candidates = list(candidates)
        if not candidates:
            candidates = store

        query_embedding = self._encode([query_text])[0]
        doc_matrix = np.stack([record.embedding for record in candidates])
        similarities = doc_matrix @ query_embedding / (
            np.linalg.norm(doc_matrix, axis=1) * np.linalg.norm(query_embedding) + 1e-10
        )

        top_indices = np.argsort(similarities)[::-1][:n_results]
        documents = [candidates[idx].document for idx in top_indices]
        metadatas = [candidates[idx].metadata for idx in top_indices]
        distances = [float(1 - similarities[idx]) for idx in top_indices]

        return {"documents": documents, "metadatas": metadatas, "distances": distances}

    def _encode(self, texts: List[str]) -> np.ndarray:
        return np.asarray(
            self.embedder.encode(
                texts,
                normalize_embeddings=True,
                batch_size=self.embedding_batch_size,
                show_progress_bar=False,
            )
        )
