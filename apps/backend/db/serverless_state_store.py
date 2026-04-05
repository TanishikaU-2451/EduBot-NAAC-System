"""Persistent state store for serverless upload and ingestion tracking."""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional, Sequence
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

import psycopg2
from psycopg2.extras import Json

logger = logging.getLogger(__name__)


class ServerlessStateStore:
    """Stores staged uploads and ingestion statuses in Postgres for serverless runtimes."""

    def __init__(
        self,
        db_url: str,
        *,
        staged_upload_ttl_minutes: int = 45,
        ingestion_status_ttl_hours: int = 24,
    ):
        if not db_url:
            raise ValueError("SUPABASE_DB_URL is required for ServerlessStateStore")

        self.db_url = db_url
        self.staged_upload_ttl_minutes = max(int(staged_upload_ttl_minutes or 45), 5)
        self.ingestion_status_ttl_hours = max(int(ingestion_status_ttl_hours or 24), 1)

        self.staged_table = "staged_uploads"
        self.status_table = "ingestion_status"

    def initialize_schema(self) -> None:
        """Create required tables and indexes if they do not exist."""
        with self._get_connection() as conn, conn.cursor() as cur:
            cur.execute(
                f"""
                CREATE TABLE IF NOT EXISTS {self.staged_table} (
                    token text PRIMARY KEY,
                    filename text NOT NULL,
                    document_type text NOT NULL,
                    file_size integer NOT NULL,
                    content bytea NOT NULL,
                    created_at timestamptz NOT NULL DEFAULT now(),
                    expires_at timestamptz NOT NULL
                );
                """
            )
            cur.execute(
                f"""
                CREATE INDEX IF NOT EXISTS idx_{self.staged_table}_expires
                ON {self.staged_table} (expires_at);
                """
            )

            cur.execute(
                f"""
                CREATE TABLE IF NOT EXISTS {self.status_table} (
                    file_path text PRIMARY KEY,
                    status text NOT NULL,
                    payload jsonb NOT NULL,
                    updated_at timestamptz NOT NULL DEFAULT now(),
                    expires_at timestamptz NOT NULL
                );
                """
            )
            cur.execute(
                f"""
                CREATE INDEX IF NOT EXISTS idx_{self.status_table}_expires
                ON {self.status_table} (expires_at);
                """
            )
            cur.execute(
                f"""
                CREATE INDEX IF NOT EXISTS idx_{self.status_table}_status
                ON {self.status_table} (status);
                """
            )
            conn.commit()

    def cleanup_expired(self) -> None:
        """Delete expired staged uploads and ingestion statuses."""
        with self._get_connection() as conn, conn.cursor() as cur:
            cur.execute(f"DELETE FROM {self.staged_table} WHERE expires_at <= now();")
            cur.execute(f"DELETE FROM {self.status_table} WHERE expires_at <= now();")
            conn.commit()

    def set_staged_upload(
        self,
        token: str,
        *,
        content: bytes,
        filename: str,
        document_type: str,
    ) -> Dict[str, Any]:
        safe_content = content or b""
        with self._get_connection() as conn, conn.cursor() as cur:
            cur.execute(
                f"""
                INSERT INTO {self.staged_table}
                (token, filename, document_type, file_size, content, expires_at)
                VALUES (%s, %s, %s, %s, %s, now() + (%s || ' minutes')::interval)
                ON CONFLICT (token) DO UPDATE
                SET filename = EXCLUDED.filename,
                    document_type = EXCLUDED.document_type,
                    file_size = EXCLUDED.file_size,
                    content = EXCLUDED.content,
                    created_at = now(),
                    expires_at = EXCLUDED.expires_at
                RETURNING token, filename, document_type, file_size, created_at;
                """,
                (
                    token,
                    filename,
                    document_type,
                    len(safe_content),
                    psycopg2.Binary(safe_content),
                    self.staged_upload_ttl_minutes,
                ),
            )
            row = cur.fetchone()
            conn.commit()

        return {
            "token": row[0],
            "filename": row[1],
            "document_type": row[2],
            "file_size": int(row[3]),
            "created_at": row[4].isoformat() if row[4] else None,
        }

    def get_staged_upload(self, token: str) -> Optional[Dict[str, Any]]:
        with self._get_connection() as conn, conn.cursor() as cur:
            cur.execute(
                f"""
                SELECT token, filename, document_type, file_size, content, created_at
                FROM {self.staged_table}
                WHERE token = %s AND expires_at > now();
                """,
                (token,),
            )
            row = cur.fetchone()

        if not row:
            return None

        raw_content = row[4]
        if isinstance(raw_content, memoryview):
            content_bytes = raw_content.tobytes()
        else:
            content_bytes = bytes(raw_content)

        return {
            "token": row[0],
            "filename": row[1],
            "document_type": row[2],
            "file_size": int(row[3]),
            "content": content_bytes,
            "created_at": row[5].isoformat() if row[5] else None,
        }

    def remove_staged_upload(self, token: str) -> Optional[Dict[str, Any]]:
        with self._get_connection() as conn, conn.cursor() as cur:
            cur.execute(
                f"""
                DELETE FROM {self.staged_table}
                WHERE token = %s
                RETURNING token, filename, document_type, file_size, created_at;
                """,
                (token,),
            )
            row = cur.fetchone()
            conn.commit()

        if not row:
            return None

        return {
            "token": row[0],
            "filename": row[1],
            "document_type": row[2],
            "file_size": int(row[3]),
            "created_at": row[4].isoformat() if row[4] else None,
        }

    def set_ingestion_status(self, file_path: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        status = str(payload.get("status") or "unknown")
        with self._get_connection() as conn, conn.cursor() as cur:
            cur.execute(
                f"""
                INSERT INTO {self.status_table}
                (file_path, status, payload, updated_at, expires_at)
                VALUES (
                    %s,
                    %s,
                    %s,
                    now(),
                    now() + (%s || ' hours')::interval
                )
                ON CONFLICT (file_path) DO UPDATE
                SET status = EXCLUDED.status,
                    payload = EXCLUDED.payload,
                    updated_at = now(),
                    expires_at = EXCLUDED.expires_at
                RETURNING payload;
                """,
                (
                    file_path,
                    status,
                    Json(payload),
                    self.ingestion_status_ttl_hours,
                ),
            )
            row = cur.fetchone()
            conn.commit()

        persisted = row[0] if row else payload
        return persisted if isinstance(persisted, dict) else payload

    def get_ingestion_statuses(self, file_paths: Sequence[str]) -> Dict[str, Dict[str, Any]]:
        paths = [str(path) for path in file_paths if str(path).strip()]
        if not paths:
            return {}

        with self._get_connection() as conn, conn.cursor() as cur:
            cur.execute(
                f"""
                SELECT file_path, payload
                FROM {self.status_table}
                WHERE file_path = ANY(%s) AND expires_at > now();
                """,
                (paths,),
            )
            rows = cur.fetchall()

        result: Dict[str, Dict[str, Any]] = {}
        for file_path, payload in rows:
            if isinstance(payload, dict):
                result[file_path] = payload
            else:
                result[file_path] = {}
        return result

    def remove_ingestion_status(self, file_path: str) -> None:
        with self._get_connection() as conn, conn.cursor() as cur:
            cur.execute(
                f"DELETE FROM {self.status_table} WHERE file_path = %s;",
                (file_path,),
            )
            conn.commit()

    def has_active_ingestion(self, active_statuses: Sequence[str]) -> bool:
        statuses = [str(status) for status in active_statuses if str(status).strip()]
        if not statuses:
            return False

        with self._get_connection() as conn, conn.cursor() as cur:
            cur.execute(
                f"""
                SELECT EXISTS(
                    SELECT 1
                    FROM {self.status_table}
                    WHERE status = ANY(%s) AND expires_at > now()
                );
                """,
                (statuses,),
            )
            row = cur.fetchone()

        return bool(row and row[0])

    def _get_connection(self):
        connection_url = self._build_connection_url(self.db_url)
        return psycopg2.connect(connection_url)

    def _build_connection_url(self, db_url: str) -> str:
        """Ensure robust SSL/statement_timeout defaults for managed Postgres connections."""
        parsed = urlparse(db_url)
        query = dict(parse_qsl(parsed.query, keep_blank_values=True))
        query.setdefault("sslmode", "require")
        query.setdefault("connect_timeout", "10")
        query.setdefault("application_name", "edubot-serverless-state")
        if "statement_timeout" not in query:
            query["options"] = "-c statement_timeout=120000"

        return urlunparse(parsed._replace(query=urlencode(query)))
