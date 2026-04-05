"""
Cross-Encoder Reranker for NAAC Compliance Intelligence System
Re-scores retrieval candidates with a joint query–document relevance model
so the most pertinent NAAC clauses and MVSR evidence rise to the top before
being handed to the LLM generator.

Pipeline position:
    Retriever (hybrid dense+lexical) → Reranker (cross-encoder) → Generator
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import List, Optional

from .retriever import RetrievalResult

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Default model — small, CPU-friendly, strong passage relevance signal
# ---------------------------------------------------------------------------
DEFAULT_RERANKER_MODEL = "cross-encoder/ms-marco-MiniLM-L-6-v2"


@dataclass
class RerankerConfig:
    """Configuration for the cross-encoder reranker."""
    enabled: bool = True
    model_name: str = DEFAULT_RERANKER_MODEL
    device: str = "cpu"
    # If True, cap the returned list at the original candidate length even when
    # the cross-encoder assigns negative scores to some entries.
    drop_negatives: bool = False


@dataclass
class RerankedResult:
    """
    Wraps a RetrievalResult with per-document cross-encoder scores appended
    to each chunk's metadata for downstream transparency / debugging.
    """
    result: RetrievalResult
    rerank_scores: List[float] = field(default_factory=list)


class ComplianceReranker:
    """
    Cross-encoder reranker that sits between the retriever and the generator.

    On first use the model is lazy-loaded so startup latency is unaffected.
    If the model cannot be loaded (missing network, low memory, etc.) the
    layer transparently becomes a no-op and logs a warning.

    Usage::

        reranker = ComplianceReranker(config)
        naac_results = reranker.rerank(query, naac_results)
        mvsr_results = reranker.rerank(query, mvsr_results)
    """

    def __init__(self, config: Optional[RerankerConfig] = None) -> None:
        self.config = config or RerankerConfig()
        self._cross_encoder = None          # lazy-loaded
        self._load_failed: bool = False     # set on first failed load attempt

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    @property
    def enabled(self) -> bool:
        return self.config.enabled

    def rerank(self, query: str, result: RetrievalResult) -> RetrievalResult:
        """
        Re-score *result* documents against *query* with the cross-encoder
        and return a new ``RetrievalResult`` sorted by descending rerank score.

        If reranking is disabled or the model is unavailable the original
        ``RetrievalResult`` is returned unchanged (zero overhead).

        The ``distances`` list in the returned result is replaced with
        ``1 - rerank_score`` so all downstream consumers (confidence scoring,
        source formatting) keep working without modification.

        Args:
            query:  The original user query string.
            result: Candidate ``RetrievalResult`` from the retriever.

        Returns:
            Re-ordered ``RetrievalResult`` with rerank scores embedded in
            each document's metadata under the key ``"reranker_score"``.
        """
        if not self.config.enabled:
            logger.debug("Reranker disabled — passing result through unchanged.")
            return result

        if not result.documents:
            return result

        cross_encoder = self._get_cross_encoder()
        if cross_encoder is None:
            logger.warning(
                "Cross-encoder unavailable — returning original retrieval order."
            )
            return result

        try:
            return self._apply_reranking(query, result, cross_encoder)
        except Exception as exc:
            logger.error(
                "Reranking failed (%s) — returning original retrieval order.", exc
            )
            return result

    def get_health(self) -> dict:
        """
        Return a health-check dict suitable for inclusion in the API
        ``/health`` endpoint response.
        """
        return {
            "enabled": self.config.enabled,
            "model": self.config.model_name,
            "device": self.config.device,
            "model_loaded": self._cross_encoder is not None,
            "load_failed": self._load_failed,
            "status": (
                "healthy"
                if (not self.config.enabled or self._cross_encoder is not None)
                else ("error" if self._load_failed else "pending")
            ),
        }

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _get_cross_encoder(self):
        """Lazy-load and cache the cross-encoder model."""
        if self._cross_encoder is not None:
            return self._cross_encoder
        if self._load_failed:
            return None

        try:
            from sentence_transformers import CrossEncoder  # type: ignore

            logger.info(
                "Loading cross-encoder reranker: %s on %s",
                self.config.model_name,
                self.config.device,
            )
            self._cross_encoder = CrossEncoder(
                self.config.model_name,
                device=self.config.device,
            )
            logger.info("Cross-encoder reranker loaded successfully.")
            return self._cross_encoder

        except Exception as exc:
            self._load_failed = True
            logger.error(
                "Failed to load cross-encoder '%s': %s. "
                "Reranking will be skipped for subsequent requests.",
                self.config.model_name,
                exc,
            )
            return None

    def _apply_reranking(
        self,
        query: str,
        result: RetrievalResult,
        cross_encoder,
    ) -> RetrievalResult:
        """
        Core reranking logic:
        1. Build (query, passage) pairs for the cross-encoder.
        2. Score all pairs in a single batch (efficient).
        3. Sort by descending score.
        4. Rebuild ``RetrievalResult`` with updated distances and metadata.
        """
        pairs = [(query, doc) for doc in result.documents]

        logger.debug(
            "Running cross-encoder on %d pairs (source: %s).",
            len(pairs),
            result.source_type,
        )

        # score() returns a numpy array of floats; higher = more relevant
        raw_scores: List[float] = cross_encoder.predict(pairs).tolist()

        # Zip with originals and sort descending by score
        ranked = sorted(
            zip(raw_scores, result.documents, result.metadatas, result.distances),
            key=lambda row: row[0],
            reverse=True,
        )

        if self.config.drop_negatives:
            ranked = [(s, d, m, dist) for s, d, m, dist in ranked if s > 0.0]

        reranked_docs: List[str] = []
        reranked_metas: List[dict] = []
        reranked_distances: List[float] = []

        for score, doc, meta, _original_dist in ranked:
            # Normalise cross-encoder score to [0, 1] using sigmoid so the
            # "distance" field stays semantically consistent with the rest of
            # the pipeline (distance = 1 - similarity).
            norm_score = _sigmoid(score)
            pseudo_distance = max(0.0, 1.0 - norm_score)

            # Embed the raw reranker score into metadata for traceability
            enriched_meta = dict(meta)
            enriched_meta["reranker_score"] = round(score, 4)
            enriched_meta["reranker_norm_score"] = round(norm_score, 4)

            reranked_docs.append(doc)
            reranked_metas.append(enriched_meta)
            reranked_distances.append(pseudo_distance)

        logger.info(
            "Reranking complete for '%s': %d → %d results.",
            result.source_type,
            len(result.documents),
            len(reranked_docs),
        )

        return RetrievalResult(
            documents=reranked_docs,
            metadatas=reranked_metas,
            distances=reranked_distances,
            source_type=result.source_type,
        )


# ---------------------------------------------------------------------------
# Utility
# ---------------------------------------------------------------------------

def _sigmoid(x: float) -> float:
    """Sigmoid to map unbounded cross-encoder logit score into (0, 1)."""
    import math
    try:
        return 1.0 / (1.0 + math.exp(-x))
    except OverflowError:
        return 0.0 if x < 0 else 1.0
