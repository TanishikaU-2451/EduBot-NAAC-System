"""
Memory layer for compliance conversations.
Stores short-term context in Postgres and long-term context in Postgres + pgvector.
"""

import json
import logging
import time
from dataclasses import dataclass
from typing import Any, Dict, List
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

import psycopg2
from psycopg2.extras import Json, execute_batch
from sentence_transformers import SentenceTransformer

logger = logging.getLogger(__name__)


@dataclass
class MemoryIdentity:
    tenant_id: str
    user_id: str
    conversation_id: str


class ConversationMemoryStore:
    """Manages short-term and long-term conversation memory."""

    def __init__(
        self,
        db_url: str,
        embedding_model: str = "all-MiniLM-L6-v2",
        embedding_dim: int = 384,
        embedding_device: str = "cpu",
        short_ttl_days: int = 7,
        long_ttl_days: int = 365,
        short_limit: int = 20,
        long_top_k: int = 6,
    ):
        if not db_url:
            raise ValueError("SUPABASE_DB_URL is required for conversation memory store")

        self.db_url = db_url
        self.embedding_dim = embedding_dim
        self.short_ttl_days = max(short_ttl_days, 1)
        self.long_ttl_days = max(long_ttl_days, 1)
        self.short_limit = max(short_limit, 1)
        self.long_top_k = max(long_top_k, 1)
        self.embedder = SentenceTransformer(embedding_model, device=embedding_device)

        self.short_table = "conversation_memory_short"
        self.long_table = "conversation_memory_long"

    def initialize_schema(self):
        """Create required memory tables and indexes if they do not exist."""
        with self._get_connection() as conn, conn.cursor() as cur:
            cur.execute("CREATE EXTENSION IF NOT EXISTS vector;")

            cur.execute(
                f"""
                CREATE TABLE IF NOT EXISTS {self.short_table} (
                    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
                    tenant_id text NOT NULL,
                    user_id text NOT NULL,
                    conversation_id text NOT NULL,
                    role text NOT NULL,
                    content text NOT NULL,
                    metadata jsonb NOT NULL DEFAULT '{{}}'::jsonb,
                    created_at timestamptz NOT NULL DEFAULT now(),
                    expires_at timestamptz NOT NULL
                );
                """
            )
            cur.execute(
                f"""
                CREATE INDEX IF NOT EXISTS idx_{self.short_table}_identity_time
                ON {self.short_table} (tenant_id, user_id, conversation_id, created_at DESC);
                """
            )
            cur.execute(
                f"""
                CREATE INDEX IF NOT EXISTS idx_{self.short_table}_expires
                ON {self.short_table} (expires_at);
                """
            )

            cur.execute(
                f"""
                CREATE TABLE IF NOT EXISTS {self.long_table} (
                    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
                    tenant_id text NOT NULL,
                    user_id text NOT NULL,
                    conversation_id text NOT NULL,
                    role text NOT NULL,
                    content text NOT NULL,
                    metadata jsonb NOT NULL DEFAULT '{{}}'::jsonb,
                    embedding vector({self.embedding_dim}) NOT NULL,
                    created_at timestamptz NOT NULL DEFAULT now(),
                    expires_at timestamptz NOT NULL
                );
                """
            )
            cur.execute(
                f"""
                CREATE INDEX IF NOT EXISTS idx_{self.long_table}_identity_time
                ON {self.long_table} (tenant_id, user_id, conversation_id, created_at DESC);
                """
            )
            cur.execute(
                f"""
                CREATE INDEX IF NOT EXISTS idx_{self.long_table}_expires
                ON {self.long_table} (expires_at);
                """
            )
            cur.execute(
                f"""
                CREATE INDEX IF NOT EXISTS idx_{self.long_table}_embedding_ivfflat
                ON {self.long_table}
                USING ivfflat (embedding vector_cosine_ops)
                WITH (lists = 100);
                """
            )
            conn.commit()

    def cleanup_expired(self):
        """Delete expired memory rows from both tables."""
        with self._get_connection() as conn, conn.cursor() as cur:
            cur.execute(f"DELETE FROM {self.short_table} WHERE expires_at <= now();")
            cur.execute(f"DELETE FROM {self.long_table} WHERE expires_at <= now();")
            conn.commit()

    def add_messages(self, identity: MemoryIdentity, messages: List[Dict[str, Any]]):
        """Persist messages to both short-term and long-term memory."""
        if not messages:
            return

        short_rows = []
        long_rows = []
        texts_for_embeddings = []

        for message in messages:
            role = str(message.get("role", "assistant")).strip() or "assistant"
            content = str(message.get("content", "")).strip()
            if not content:
                continue

            metadata = message.get("metadata", {})
            if not isinstance(metadata, dict):
                metadata = {}

            short_rows.append(
                (
                    identity.tenant_id,
                    identity.user_id,
                    identity.conversation_id,
                    role,
                    content,
                    Json(metadata),
                    self.short_ttl_days,
                )
            )
            texts_for_embeddings.append(content)
            long_rows.append((role, content, Json(metadata), self.long_ttl_days))

        if not short_rows:
            return

        embeddings = self.embedder.encode(texts_for_embeddings, normalize_embeddings=False)

        with self._get_connection() as conn, conn.cursor() as cur:
            execute_batch(
                cur,
                f"""
                INSERT INTO {self.short_table}
                (tenant_id, user_id, conversation_id, role, content, metadata, expires_at)
                VALUES (%s, %s, %s, %s, %s, %s, now() + (%s || ' days')::interval);
                """,
                short_rows,
                page_size=200,
            )

            long_insert_rows = []
            for (role, content, metadata, ttl_days), embedding in zip(long_rows, embeddings):
                long_insert_rows.append(
                    (
                        identity.tenant_id,
                        identity.user_id,
                        identity.conversation_id,
                        role,
                        content,
                        metadata,
                        self._to_vector_literal(embedding),
                        ttl_days,
                    )
                )

            execute_batch(
                cur,
                f"""
                INSERT INTO {self.long_table}
                (tenant_id, user_id, conversation_id, role, content, metadata, embedding, expires_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s::vector, now() + (%s || ' days')::interval);
                """,
                long_insert_rows,
                page_size=200,
            )
            conn.commit()

    def get_context(self, identity: MemoryIdentity, query_text: str) -> Dict[str, List[Dict[str, Any]]]:
        """Fetch short-term chronological context and long-term semantic context."""
        short_memories: List[Dict[str, Any]] = []
        long_memories: List[Dict[str, Any]] = []

        with self._get_connection() as conn, conn.cursor() as cur:
            cur.execute(
                f"""
                SELECT role, content, metadata, created_at
                FROM {self.short_table}
                WHERE tenant_id = %s AND user_id = %s AND conversation_id = %s
                  AND expires_at > now()
                ORDER BY created_at DESC
                LIMIT %s;
                """,
                (identity.tenant_id, identity.user_id, identity.conversation_id, self.short_limit),
            )
            short_rows = cur.fetchall()

            for role, content, metadata, created_at in reversed(short_rows):
                short_memories.append(
                    {
                        "role": role,
                        "content": content,
                        "metadata": self._metadata_to_dict(metadata),
                        "created_at": created_at.isoformat() if created_at else None,
                    }
                )

            query_embedding = self.embedder.encode([query_text], normalize_embeddings=False)[0]
            emb_str = self._to_vector_literal(query_embedding)
            cur.execute(
                f"""
                SELECT role, content, metadata, created_at, (embedding <=> %s::vector) AS distance
                FROM {self.long_table}
                WHERE tenant_id = %s AND user_id = %s AND conversation_id = %s
                  AND expires_at > now()
                ORDER BY embedding <=> %s::vector
                LIMIT %s;
                """,
                (
                    emb_str,
                    identity.tenant_id,
                    identity.user_id,
                    identity.conversation_id,
                    emb_str,
                    self.long_top_k,
                ),
            )
            long_rows = cur.fetchall()

            for role, content, metadata, created_at, distance in long_rows:
                long_memories.append(
                    {
                        "role": role,
                        "content": content,
                        "metadata": self._metadata_to_dict(metadata),
                        "created_at": created_at.isoformat() if created_at else None,
                        "similarity": round(1 - float(distance), 4),
                    }
                )

        return {"short_term": short_memories, "long_term": long_memories}

    def get_health(self) -> Dict[str, Any]:
        """Memory layer health details."""
        started = time.time()
        try:
            with self._get_connection() as conn, conn.cursor() as cur:
                cur.execute(f"SELECT COUNT(*) FROM {self.short_table};")
                short_count = int(cur.fetchone()[0])
                cur.execute(f"SELECT COUNT(*) FROM {self.long_table};")
                long_count = int(cur.fetchone()[0])
            return {
                "ok": True,
                "short_rows": short_count,
                "long_rows": long_count,
                "latency_ms": round((time.time() - started) * 1000, 2),
            }
        except Exception as e:
            logger.exception("Memory health check failed")
            return {
                "ok": False,
                "error": str(e),
                "latency_ms": round((time.time() - started) * 1000, 2),
            }

    def clear_short_term_memory(self) -> None:
        """Clear all short-term conversation memory (used on backend startup)."""
        logger.info("Clearing short-term conversation memory table.")
        try:
            with self._get_connection() as conn, conn.cursor() as cur:
                cur.execute(f"TRUNCATE TABLE {self.short_table};")
            logger.info("Short-term memory cleared.")
        except Exception as e:
            logger.error("Failed to clear short-term memory: %s", e)

    def _metadata_to_dict(self, metadata: Any) -> Dict[str, Any]:
        if isinstance(metadata, dict):
            return metadata
        if isinstance(metadata, str):
            try:
                parsed = json.loads(metadata)
                if isinstance(parsed, dict):
                    return parsed
            except Exception:
                return {}
        return {}

    def _get_connection(self):
        return psycopg2.connect(self._build_connection_url(self.db_url))

    def _build_connection_url(self, db_url: str) -> str:
        parsed = urlparse(db_url)
        query = dict(parse_qsl(parsed.query, keep_blank_values=True))
        query.setdefault("sslmode", "require")
        query.setdefault("connect_timeout", "10")
        updated = parsed._replace(query=urlencode(query))
        return urlunparse(updated)

    def _to_vector_literal(self, embedding) -> str:
        values = ",".join(f"{float(x):.6f}" for x in embedding)
        return f"[{values}]"

