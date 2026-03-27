"""
Supabase pgvector-backed store for NAAC Compliance Intelligence System.
Replaces local Chroma with Postgres+pgvector hosted on Supabase.
"""

import json
import logging
import time
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse
from typing import Any, Dict, List, Optional, Tuple

import psycopg2
from psycopg2.extras import Json
from sentence_transformers import SentenceTransformer

logger = logging.getLogger(__name__)


class SupabaseVectorStore:
    """Minimal pgvector store wrapper using psycopg2."""

    def __init__(
        self,
        db_url: str,
        table_name: str = "chunks",
        embedding_model: str = "all-MiniLM-L6-v2",
        embedding_dim: int = 384,
        embedding_device: str = "cpu",
    ):
        if not db_url:
            raise ValueError("SUPABASE_DB_URL is required for SupabaseVectorStore")

        self.db_url = db_url
        self.table_name = table_name
        self.embedding_dim = embedding_dim
        self.embedder = SentenceTransformer(embedding_model, device=embedding_device)

        logger.info(
            "Supabase vector store initialized (table=%s, model=%s, dim=%s)",
            table_name,
            embedding_model,
            embedding_dim,
        )

    def health_check(self) -> Dict[str, Any]:
        """Run a lightweight DB and table check for diagnostics."""
        started = time.time()
        try:
            with self._get_connection() as conn, conn.cursor() as cur:
                cur.execute("SELECT 1;")
                _ = cur.fetchone()

                cur.execute(
                    """
                    SELECT EXISTS (
                        SELECT 1
                        FROM information_schema.tables
                        WHERE table_schema = 'public' AND table_name = %s
                    );
                    """,
                    (self.table_name,),
                )
                table_exists = bool(cur.fetchone()[0])

                result: Dict[str, Any] = {
                    "ok": table_exists,
                    "table": self.table_name,
                    "table_exists": table_exists,
                    "latency_ms": round((time.time() - started) * 1000, 2),
                }

                if table_exists:
                    cur.execute(f"SELECT COUNT(*) FROM {self.table_name};")
                    result["total_rows"] = int(cur.fetchone()[0])

                return result
        except Exception as e:
            logger.exception("Supabase health check failed")
            return {
                "ok": False,
                "table": self.table_name,
                "table_exists": False,
                "error": str(e),
                "latency_ms": round((time.time() - started) * 1000, 2),
            }

    # Public API mirrors the old ChromaVectorStore
    def add_naac_documents(self, documents: List[str], metadatas: List[Dict[str, Any]]):
        self._add_documents(documents, metadatas, doc_type="naac_requirement")

    def add_mvsr_documents(self, documents: List[str], metadatas: List[Dict[str, Any]]):
        self._add_documents(documents, metadatas, doc_type="mvsr_evidence")

    def query_naac_requirements(
        self,
        query_text: str,
        n_results: int = 5,
        criterion_filter: Optional[str] = None,
    ) -> Dict[str, Any]:
        return self._query(
            query_text,
            n_results,
            doc_type="naac_requirement",
            criterion_filter=criterion_filter,
        )

    def query_mvsr_evidence(
        self,
        query_text: str,
        n_results: int = 5,
        category_filter: Optional[str] = None,
    ) -> Dict[str, Any]:
        return self._query(
            query_text,
            n_results,
            doc_type="mvsr_evidence",
            category_filter=category_filter,
        )

    def get_collection_stats(self) -> Dict[str, int]:
        started = time.time()
        sql = f"""
            SELECT doc_type, COUNT(*)
            FROM {self.table_name}
            GROUP BY doc_type;
        """
        counts = {"naac_requirements_count": 0, "mvsr_evidence_count": 0, "total_documents": 0}

        with self._get_connection() as conn, conn.cursor() as cur:
            cur.execute(sql)
            rows = cur.fetchall()
            for doc_type, count in rows:
                if doc_type == "naac_requirement":
                    counts["naac_requirements_count"] = count
                elif doc_type == "mvsr_evidence":
                    counts["mvsr_evidence_count"] = count
                counts["total_documents"] += count

        logger.info(
            "Supabase stats fetched: naac=%s mvsr=%s total=%s (%.2fms)",
            counts["naac_requirements_count"],
            counts["mvsr_evidence_count"],
            counts["total_documents"],
            (time.time() - started) * 1000,
        )
        return counts

    def update_naac_version(self, old_version: str, new_version: str):
        """Archive old NAAC version entries by tagging metadata; no deletion."""
        sql = f"""
            UPDATE {self.table_name}
            SET metadata = metadata || jsonb_build_object('status', 'archived', 'archived_version', %s)
            WHERE doc_type = 'naac_requirement' AND (metadata->>'version') = %s;
        """

        with self._get_connection() as conn, conn.cursor() as cur:
            cur.execute(sql, (old_version, old_version))
            conn.commit()

        logger.info("Archived NAAC version %s", old_version)

    def consolidate_single_row_mode(self):
        """Collapse historical multi-row chunk data into one row per doc_type."""
        for doc_type in ["naac_requirement", "mvsr_evidence"]:
            with self._get_connection() as conn, conn.cursor() as cur:
                cur.execute(
                    f"SELECT content, metadata FROM {self.table_name} WHERE doc_type = %s",
                    (doc_type,),
                )
                rows = cur.fetchall()

            if len(rows) <= 1:
                continue

            docs: List[str] = []
            metas: List[Dict[str, Any]] = []
            for content, metadata in rows:
                if content and str(content).strip():
                    docs.append(str(content).strip())

                if isinstance(metadata, dict):
                    metas.append(metadata)
                elif isinstance(metadata, str):
                    try:
                        parsed = json.loads(metadata)
                        if isinstance(parsed, dict):
                            metas.append(parsed)
                        else:
                            metas.append({})
                    except Exception:
                        metas.append({})
                else:
                    metas.append({})

            if docs and metas and len(docs) == len(metas):
                self._add_documents(docs, metas, doc_type)
                logger.info(
                    "Consolidated %s rows into one row for %s",
                    len(rows),
                    doc_type,
                )

    # Internal helpers
    def _add_documents(self, documents: List[str], metadatas: List[Dict[str, Any]], doc_type: str):
        if not documents or not metadatas:
            logger.warning("No documents/metadatas provided for %s", doc_type)
            return

        if len(documents) != len(metadatas):
            raise ValueError("Documents and metadatas must have the same length")

        started = time.time()
        logger.info("Upserting single aggregated row for %s from %s input documents", doc_type, len(documents))

        incoming_docs = [doc.strip() for doc in documents if doc and doc.strip()]
        if not incoming_docs:
            logger.warning("All provided documents were empty after cleanup for %s", doc_type)
            return

        incoming_content = "\n\n".join(incoming_docs)

        with self._get_connection() as conn, conn.cursor() as cur:
            cur.execute(
                f"SELECT content, metadata FROM {self.table_name} WHERE doc_type = %s",
                (doc_type,),
            )
            existing_rows = cur.fetchall()

            if existing_rows:
                existing_text_parts: List[str] = []
                existing_sources: List[str] = []
                existing_criteria: List[str] = []
                existing_categories: List[str] = []
                for existing_content, existing_meta in existing_rows:
                    if existing_content:
                        existing_text_parts.append(str(existing_content))

                    meta_dict: Dict[str, Any] = {}
                    if isinstance(existing_meta, dict):
                        meta_dict = existing_meta
                    elif isinstance(existing_meta, str):
                        try:
                            loaded = json.loads(existing_meta)
                            if isinstance(loaded, dict):
                                meta_dict = loaded
                        except Exception:
                            meta_dict = {}

                    src_list = meta_dict.get("source_files", [])
                    if isinstance(src_list, list):
                        existing_sources.extend(str(x) for x in src_list if str(x).strip())
                    src_single = str(meta_dict.get("source_file", "")).strip()
                    if src_single:
                        existing_sources.append(src_single)

                    criterion_list = meta_dict.get("criteria", [])
                    if isinstance(criterion_list, list):
                        existing_criteria.extend(str(x) for x in criterion_list if str(x).strip())
                    criterion_single = str(meta_dict.get("criterion", "")).strip()
                    if criterion_single:
                        existing_criteria.append(criterion_single)

                    category_list = meta_dict.get("categories", [])
                    if isinstance(category_list, list):
                        existing_categories.extend(str(x) for x in category_list if str(x).strip())
                    category_single = str(meta_dict.get("category", "")).strip()
                    if category_single:
                        existing_categories.append(category_single)

                existing_combined = "\n\n".join(part.strip() for part in existing_text_parts if part and part.strip())
                merged_content = self._merge_text(existing_combined, incoming_content)
                existing_meta_merged = {
                    "source_files": sorted(set(existing_sources)),
                    "criteria": sorted(set(existing_criteria)),
                    "categories": sorted(set(existing_categories)),
                }
                merged_meta = self._build_single_row_metadata(doc_type, metadatas, existing_meta_merged)
            else:
                merged_content = incoming_content
                merged_meta = self._build_single_row_metadata(doc_type, metadatas, None)

            embedding = self.embedder.encode([merged_content], normalize_embeddings=False)[0]
            emb_str = self._to_vector_literal(embedding)

            # Enforce exactly one row per document type.
            cur.execute(f"DELETE FROM {self.table_name} WHERE doc_type = %s", (doc_type,))
            cur.execute(
                f"""
                INSERT INTO {self.table_name} (doc_type, content, metadata, embedding)
                VALUES (%s, %s, %s, %s::vector)
                """,
                (doc_type, merged_content, Json(merged_meta), emb_str),
            )
            conn.commit()

        logger.info(
            "Upserted single %s row (chars=%s, %.2fms)",
            doc_type,
            len(merged_content),
            (time.time() - started) * 1000,
        )

    def _query(
        self,
        query_text: str,
        n_results: int,
        doc_type: str,
        criterion_filter: Optional[str] = None,
        category_filter: Optional[str] = None,
    ) -> Dict[str, Any]:
        started = time.time()
        logger.info(
            "Supabase query start: type=%s n_results=%s criterion=%s category=%s",
            doc_type,
            n_results,
            criterion_filter,
            category_filter,
        )

        query_embedding = self.embedder.encode([query_text], normalize_embeddings=False)[0]
        emb_str = self._to_vector_literal(query_embedding)

        where_clauses = ["doc_type = %s"]
        params: List[Any] = [doc_type]

        if criterion_filter:
            where_clauses.append("(metadata->>'criterion') = %s")
            params.append(criterion_filter)
        if category_filter:
            where_clauses.append("(metadata->>'category') = %s")
            params.append(category_filter)

        where_sql = " AND ".join(where_clauses)

        sql = f"""
            SELECT content, metadata, (embedding <=> %s::vector) AS distance
            FROM {self.table_name}
            WHERE {where_sql}
            ORDER BY embedding <=> %s::vector
            LIMIT %s;
        """

        documents: List[str] = []
        metadatas: List[Dict[str, Any]] = []
        distances: List[float] = []

        with self._get_connection() as conn, conn.cursor() as cur:
            cur.execute(sql, [emb_str, *params, emb_str, n_results])
            rows = cur.fetchall()

            # In single-row mode, filters may not match aggregate metadata exactly.
            # Fall back to the single best row for this doc_type.
            if not rows and (criterion_filter or category_filter):
                cur.execute(
                    f"""
                    SELECT content, metadata, (embedding <=> %s::vector) AS distance
                    FROM {self.table_name}
                    WHERE doc_type = %s
                    ORDER BY embedding <=> %s::vector
                    LIMIT 1;
                    """,
                    [emb_str, doc_type, emb_str],
                )
                rows = cur.fetchall()

            for content, metadata, distance in rows:
                documents.append(content)
                metadatas.append(metadata if isinstance(metadata, dict) else json.loads(metadata))
                distances.append(float(distance))

            logger.info(
                "Supabase query completed: rows=%s (%.2fms)",
                len(documents),
                (time.time() - started) * 1000,
            )

        return {"documents": documents, "metadatas": metadatas, "distances": distances}

    def _get_connection(self):
        logger.debug("Opening Supabase Postgres connection")
        connection_url = self._build_connection_url(self.db_url)
        return psycopg2.connect(connection_url)

    def _build_connection_url(self, db_url: str) -> str:
        """Ensure Supabase-safe connection settings exist in URL."""
        parsed = urlparse(db_url)
        query = dict(parse_qsl(parsed.query, keep_blank_values=True))

        # Supabase pooler requires TLS.
        query.setdefault("sslmode", "require")
        # Fail fast on unreachable endpoints.
        query.setdefault("connect_timeout", "10")

        updated = parsed._replace(query=urlencode(query))
        return urlunparse(updated)

    def _to_vector_literal(self, embedding) -> str:
        # pgvector accepts '[1,2,3]' literal
        values = ",".join(f"{float(x):.6f}" for x in embedding)
        return f"[{values}]"

    def _merge_text(self, existing: str, incoming: str) -> str:
        existing_clean = (existing or "").strip()
        incoming_clean = (incoming or "").strip()

        if not existing_clean:
            return incoming_clean
        if not incoming_clean:
            return existing_clean
        if incoming_clean in existing_clean:
            return existing_clean
        return f"{existing_clean}\n\n{incoming_clean}"

    def _build_single_row_metadata(
        self,
        doc_type: str,
        metadatas: List[Dict[str, Any]],
        existing_metadata: Optional[Any],
    ) -> Dict[str, Any]:
        existing_dict: Dict[str, Any] = {}
        if isinstance(existing_metadata, dict):
            existing_dict = existing_metadata
        elif isinstance(existing_metadata, str):
            try:
                parsed = json.loads(existing_metadata)
                if isinstance(parsed, dict):
                    existing_dict = parsed
            except Exception:
                existing_dict = {}

        existing_sources = existing_dict.get("source_files", [])
        if not isinstance(existing_sources, list):
            existing_sources = []

        new_sources: List[str] = []
        criteria: List[str] = []
        categories: List[str] = []

        for meta in metadatas:
            src = str(meta.get("source_file", "")).strip()
            if src:
                new_sources.append(src)

            criterion = str(meta.get("criterion", "")).strip()
            if criterion:
                criteria.append(criterion)

            category = str(meta.get("category", "")).strip()
            if category:
                categories.append(category)

        merged_sources = sorted({*existing_sources, *new_sources})
        merged_criteria = sorted({*([str(x) for x in existing_dict.get("criteria", [])] if isinstance(existing_dict.get("criteria"), list) else []), *criteria})
        merged_categories = sorted({*([str(x) for x in existing_dict.get("categories", [])] if isinstance(existing_dict.get("categories"), list) else []), *categories})

        return {
            "type": doc_type,
            "storage_mode": "single_row",
            "updated_at": int(time.time()),
            "source_files": merged_sources,
            "source_count": len(merged_sources),
            "criteria": merged_criteria,
            "categories": merged_categories,
            "aggregated_from_inputs": len(metadatas),
        }
