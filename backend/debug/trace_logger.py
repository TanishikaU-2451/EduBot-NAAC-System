"""Trace logging helpers for ingestion and query debugging."""

from __future__ import annotations

import json
import logging
import re
from dataclasses import asdict, is_dataclass
from datetime import datetime
from functools import lru_cache
from pathlib import Path
from threading import Lock
from typing import Any, Optional
from uuid import uuid4

from ..config.settings import get_settings

logger = logging.getLogger(__name__)


class PipelineTraceLogger:
    """Write per-run debugging artifacts to disk."""

    def __init__(self, enabled: bool, base_dir: Path):
        self.enabled = bool(enabled)
        self.base_dir = Path(base_dir)
        self._lock = Lock()

        if self.enabled:
            self.base_dir.mkdir(parents=True, exist_ok=True)

    def create_trace_id(self, prefix: str, label: Optional[str] = None) -> str:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        safe_prefix = self._sanitize(prefix) or "trace"
        safe_label = self._sanitize(label or "")
        suffix = uuid4().hex[:8]

        parts = [safe_prefix, timestamp]
        if safe_label:
            parts.append(safe_label[:48])
        parts.append(suffix)
        return "__".join(parts)

    def get_trace_dir(self, trace_id: str) -> Path:
        trace_dir = self.base_dir / trace_id
        if self.enabled:
            with self._lock:
                trace_dir.mkdir(parents=True, exist_ok=True)
        return trace_dir

    def write_json(self, trace_id: str, filename: str, payload: Any) -> Optional[Path]:
        if not self.enabled or not trace_id:
            return None

        try:
            file_path = self.get_trace_dir(trace_id) / filename
            file_path.write_text(
                json.dumps(self._make_json_safe(payload), indent=2, ensure_ascii=False),
                encoding="utf-8",
            )
            return file_path
        except Exception as exc:
            logger.warning("Failed to write trace json %s/%s: %s", trace_id, filename, exc)
            return None

    def write_text(self, trace_id: str, filename: str, text: str) -> Optional[Path]:
        if not self.enabled or not trace_id:
            return None

        try:
            file_path = self.get_trace_dir(trace_id) / filename
            file_path.write_text(text or "", encoding="utf-8")
            return file_path
        except Exception as exc:
            logger.warning("Failed to write trace text %s/%s: %s", trace_id, filename, exc)
            return None

    def write_error(self, trace_id: str, message: str, **extra: Any) -> Optional[Path]:
        payload = {
            "timestamp": datetime.now().isoformat(),
            "error": message,
            **extra,
        }
        return self.write_json(trace_id, "99_error.json", payload)

    def _make_json_safe(self, value: Any) -> Any:
        if value is None or isinstance(value, (str, int, float, bool)):
            return value

        if isinstance(value, Path):
            return str(value)

        if isinstance(value, datetime):
            return value.isoformat()

        if is_dataclass(value):
            return self._make_json_safe(asdict(value))

        if isinstance(value, dict):
            return {
                str(key): self._make_json_safe(item)
                for key, item in value.items()
            }

        if isinstance(value, (list, tuple, set)):
            return [self._make_json_safe(item) for item in value]

        return str(value)

    def _sanitize(self, value: str) -> str:
        cleaned = re.sub(r"[^a-zA-Z0-9._-]+", "_", (value or "").strip())
        cleaned = re.sub(r"_+", "_", cleaned).strip("._-")
        return cleaned.lower()


@lru_cache(maxsize=1)
def get_pipeline_trace_logger() -> PipelineTraceLogger:
    settings = get_settings()
    return PipelineTraceLogger(
        enabled=settings.pipeline_debug_enabled,
        base_dir=Path(settings.pipeline_debug_dir),
    )
