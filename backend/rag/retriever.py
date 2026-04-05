"""
RAG Retriever Component for NAAC Compliance Intelligence System
Handles semantic retrieval from both NAAC requirements and MVSR evidence collections
"""

from typing import List, Dict, Any, Optional, Tuple
import logging
from dataclasses import dataclass
import re

from typing import Protocol


class VectorStore(Protocol):
    def query_naac_requirements(self, query_text: str, n_results: int = 5, criterion_filter: Optional[str] = None) -> Dict[str, Any]: ...
    def query_mvsr_evidence(self, query_text: str, n_results: int = 5, category_filter: Optional[str] = None) -> Dict[str, Any]: ...

logger = logging.getLogger(__name__)

@dataclass
class RetrievalResult:
    """Structure for retrieval results"""
    documents: List[str]
    metadatas: List[Dict[str, Any]]
    distances: List[float]
    source_type: str  # 'naac_requirement' or 'mvsr_evidence'
    used_threshold_fallback: bool = False
    retrieval_notes: Optional[List[str]] = None

class ComplianceRetriever:
    """
    Intelligent retriever for NAAC compliance queries
    Performs semantic retrieval from separated NAAC and MVSR collections
    """
    
    def __init__(self, 
                 chroma_store: VectorStore,
                 default_k_naac: int = 5,
                 default_k_mvsr: int = 5,
                 similarity_threshold: float = 0.3):
        """
        Initialize the retriever
        
        Args:
            chroma_store: ChromaDB vector store instance
            default_k_naac: Default number of NAAC documents to retrieve
            default_k_mvsr: Default number of MVSR documents to retrieve  
            similarity_threshold: Minimum similarity score for results
        """
        self.chroma_store = chroma_store
        self.default_k_naac = default_k_naac
        self.default_k_mvsr = default_k_mvsr
        self.similarity_threshold = similarity_threshold
    
    def retrieve_compliance_context(self, 
                                  query: str,
                                  k_naac: Optional[int] = None,
                                  k_mvsr: Optional[int] = None,
                                  criterion_filter: Optional[str] = None,
                                  category_filter: Optional[str] = None) -> Tuple[RetrievalResult, RetrievalResult]:
        """
        Retrieve relevant context from both NAAC and MVSR collections
        
        Args:
            query: Natural language query
            k_naac: Number of NAAC documents to retrieve
            k_mvsr: Number of MVSR documents to retrieve
            criterion_filter: Filter NAAC results by criterion (e.g., "2")
            category_filter: Filter MVSR results by category (e.g., "policies")
            
        Returns:
            Tuple of (naac_results, mvsr_results)
        """
        k_naac = k_naac or self.default_k_naac
        k_mvsr = k_mvsr or self.default_k_mvsr
        
        logger.info(f"Retrieving compliance context for query: '{query[:100]}...'")
        
        # Retrieve from NAAC requirements
        naac_results = self._retrieve_naac_requirements(
            query, k_naac, criterion_filter
        )
        
        # Retrieve from MVSR evidence  
        mvsr_results = self._retrieve_mvsr_evidence(
            query, k_mvsr, category_filter
        )
        
        logger.info(f"Retrieved {len(naac_results.documents)} NAAC and {len(mvsr_results.documents)} MVSR documents")
        
        return naac_results, mvsr_results

    def retrieve_compliance_context_hybrid(
        self,
        query: str,
        k_naac: Optional[int] = None,
        k_mvsr: Optional[int] = None,
        criterion_filter: Optional[str] = None,
        category_filter: Optional[str] = None,
        dense_weight: float = 0.65,
        lexical_weight: float = 0.35,
        candidate_multiplier: int = 4,
    ) -> Tuple[RetrievalResult, RetrievalResult]:
        """
        Hybrid retrieval using dense search candidates reranked with lexical overlap.

        This is useful for compliance checking where exact phrases/conditions matter.
        """
        k_naac = k_naac or self.default_k_naac
        k_mvsr = k_mvsr or self.default_k_mvsr
        candidate_multiplier = max(int(candidate_multiplier or 1), 1)

        candidate_k_naac = max(k_naac * candidate_multiplier, k_naac)
        candidate_k_mvsr = max(k_mvsr * candidate_multiplier, k_mvsr)

        logger.info(
            f"Hybrid retrieval for query: '{query[:100]}...' (dense={dense_weight:.2f}, lexical={lexical_weight:.2f})"
        )

        # Step 1: fetch larger dense candidate pools
        naac_candidates = self._retrieve_naac_requirements(query, candidate_k_naac, criterion_filter)
        mvsr_candidates = self._retrieve_mvsr_evidence(query, candidate_k_mvsr, category_filter)

        # Step 2: rerank candidates with hybrid score
        naac_results = self._hybrid_rerank(query, naac_candidates, k_naac, dense_weight, lexical_weight)
        mvsr_results = self._hybrid_rerank(query, mvsr_candidates, k_mvsr, dense_weight, lexical_weight)

        logger.info(
            f"Hybrid retrieved {len(naac_results.documents)} NAAC and {len(mvsr_results.documents)} MVSR documents"
        )

        return naac_results, mvsr_results
    
    def _retrieve_naac_requirements(self, 
                                  query: str,
                                  k: int,
                                  criterion_filter: Optional[str] = None) -> RetrievalResult:
        """Retrieve from NAAC requirements collection"""
        
        try:
            results = self.chroma_store.query_naac_requirements(
                query_text=query,
                n_results=k,
                criterion_filter=criterion_filter
            )
            
            # Filter results by similarity threshold
            filtered_docs, filtered_metadatas, filtered_distances, filter_info = self._filter_by_similarity(
                results['documents'],
                results['metadatas'], 
                results['distances']
            )
            
            return RetrievalResult(
                documents=filtered_docs,
                metadatas=filtered_metadatas,
                distances=filtered_distances,
                source_type='naac_requirement',
                used_threshold_fallback=filter_info["used_fallback"],
                retrieval_notes=filter_info["notes"],
            )
            
        except Exception as e:
            logger.error(f"Error retrieving NAAC requirements: {e}")
            return RetrievalResult([], [], [], 'naac_requirement')
    
    def _retrieve_mvsr_evidence(self, 
                              query: str,
                              k: int, 
                              category_filter: Optional[str] = None) -> RetrievalResult:
        """Retrieve from MVSR evidence collection"""
        
        try:
            results = self.chroma_store.query_mvsr_evidence(
                query_text=query,
                n_results=k,
                category_filter=category_filter
            )
            
            # Filter results by similarity threshold
            filtered_docs, filtered_metadatas, filtered_distances, filter_info = self._filter_by_similarity(
                results['documents'],
                results['metadatas'],
                results['distances']
            )
            
            return RetrievalResult(
                documents=filtered_docs,
                metadatas=filtered_metadatas,
                distances=filtered_distances,
                source_type='mvsr_evidence',
                used_threshold_fallback=filter_info["used_fallback"],
                retrieval_notes=filter_info["notes"],
            )
            
        except Exception as e:
            logger.error(f"Error retrieving MVSR evidence: {e}")
            return RetrievalResult([], [], [], 'mvsr_evidence')
    
    def _filter_by_similarity(self, 
                            documents: List[str],
                            metadatas: List[Dict[str, Any]], 
                            distances: List[float]) -> Tuple[List[str], List[Dict[str, Any]], List[float], Dict[str, Any]]:
        """Filter results based on similarity threshold"""
        
        if not documents or not distances:
            return [], [], [], {"used_fallback": False, "notes": []}
        
        # ChromaDB uses distance (lower is better), convert to similarity
        # Assuming cosine distance: similarity = 1 - distance
        similarities = [1 - dist for dist in distances]
        
        # Filter by threshold
        filtered_docs = []
        filtered_metadatas = [] 
        filtered_distances = []
        notes: List[str] = []
        
        for i, similarity in enumerate(similarities):
            if similarity >= self.similarity_threshold:
                filtered_docs.append(documents[i])
                filtered_metadatas.append(metadatas[i])
                filtered_distances.append(distances[i])

        filtered_docs, filtered_metadatas, filtered_distances = self._deduplicate_results(
            filtered_docs,
            filtered_metadatas,
            filtered_distances,
        )

        used_fallback = False
        if not filtered_docs:
            fallback_count = min(3, len(documents))
            filtered_docs, filtered_metadatas, filtered_distances = self._deduplicate_results(
                documents[:fallback_count],
                metadatas[:fallback_count],
                distances[:fallback_count],
            )
            used_fallback = bool(filtered_docs)
            if used_fallback:
                best_similarity = max(similarities)
                notes.append(
                    "No results met the configured similarity threshold "
                    f"({self.similarity_threshold:.2f}); preserved the top {len(filtered_docs)} "
                    f"candidate(s) instead. Best similarity was {best_similarity:.4f}."
                )
                logger.warning(
                    "No retrieval hits met similarity threshold %.2f; preserving top %s candidate(s). Best similarity %.4f",
                    self.similarity_threshold,
                    len(filtered_docs),
                    best_similarity,
                )
        
        logger.debug(f"Filtered {len(documents)} -> {len(filtered_docs)} results by similarity threshold")
        
        return filtered_docs, filtered_metadatas, filtered_distances, {
            "used_fallback": used_fallback,
            "notes": notes,
        }

    def _hybrid_rerank(
        self,
        query: str,
        candidates: RetrievalResult,
        top_k: int,
        dense_weight: float,
        lexical_weight: float,
    ) -> RetrievalResult:
        """Rerank dense candidates with lexical token overlap and return top-k."""
        if not candidates.documents:
            return candidates

        # Normalize weights to avoid accidental misconfiguration.
        total_weight = max(dense_weight + lexical_weight, 1e-9)
        dense_weight = dense_weight / total_weight
        lexical_weight = lexical_weight / total_weight

        query_tokens = self._tokenize_text(query)
        scored_rows = []

        for doc, meta, dist in zip(candidates.documents, candidates.metadatas, candidates.distances):
            dense_similarity = max(0.0, 1 - dist)
            lexical_similarity = self._lexical_overlap_score(query_tokens, self._tokenize_text(doc))
            hybrid_score = (dense_weight * dense_similarity) + (lexical_weight * lexical_similarity)

            # We DO NOT apply the similarity threshold again here!
            # It unfairly punishes documents with 0 exact keyword overlap despite dense hits.
            scored_rows.append((hybrid_score, doc, meta, dist))

        scored_rows.sort(key=lambda item: item[0], reverse=True)
        top_rows = scored_rows[:top_k]

        documents, metadatas, distances = self._deduplicate_results(
            [row[1] for row in top_rows],
            [row[2] for row in top_rows],
            [row[3] for row in top_rows],
        )

        return RetrievalResult(
            documents=documents,
            metadatas=metadatas,
            distances=distances,
            source_type=candidates.source_type,
            used_threshold_fallback=candidates.used_threshold_fallback,
            retrieval_notes=candidates.retrieval_notes,
        )

    def _deduplicate_results(
        self,
        documents: List[str],
        metadatas: List[Dict[str, Any]],
        distances: List[float],
    ) -> Tuple[List[str], List[Dict[str, Any]], List[float]]:
        """Remove duplicate and near-duplicate retrieval hits."""
        unique_docs: List[str] = []
        unique_metadatas: List[Dict[str, Any]] = []
        unique_distances: List[float] = []
        seen_doc_fingerprints = set()
        seen_section_fingerprints = set()

        for doc, meta, distance in zip(documents, metadatas, distances):
            doc_fingerprint = self._document_fingerprint(doc)
            section_fingerprint = self._section_fingerprint(meta)

            if doc_fingerprint and doc_fingerprint in seen_doc_fingerprints:
                continue
            if section_fingerprint and section_fingerprint in seen_section_fingerprints:
                continue

            if doc_fingerprint:
                seen_doc_fingerprints.add(doc_fingerprint)
            if section_fingerprint:
                seen_section_fingerprints.add(section_fingerprint)

            unique_docs.append(doc)
            unique_metadatas.append(meta)
            unique_distances.append(distance)

        return unique_docs, unique_metadatas, unique_distances

    def _document_fingerprint(self, text: str) -> str:
        """Build a stable text fingerprint to collapse near-identical chunks."""
        normalized = re.sub(r"\s+", " ", (text or "").lower()).strip()
        normalized = re.sub(r"[^a-z0-9 ]+", "", normalized)
        return normalized[:240]

    def _section_fingerprint(self, metadata: Dict[str, Any]) -> str:
        """Build a metadata-based fingerprint for logical section deduplication."""
        source = str(
            metadata.get("source_file")
            or metadata.get("file_name")
            or metadata.get("document_title")
            or metadata.get("document")
            or ""
        ).strip().lower()
        header = str(
            metadata.get("section_header")
            or metadata.get("document_title")
            or metadata.get("document")
            or ""
        ).strip().lower()
        start_page = metadata.get("start_page")
        end_page = metadata.get("end_page")

        if not source and not header:
            return ""

        return f"{source}|{header}|{start_page}|{end_page}"

    def _tokenize_text(self, text: str) -> List[str]:
        """Simple normalized tokenizer tuned for rule/condition-style queries."""
        return re.findall(r"[a-z0-9]+", (text or "").lower())

    def _lexical_overlap_score(self, query_tokens: List[str], doc_tokens: List[str]) -> float:
        """Compute lexical overlap score as recall-style token coverage."""
        if not query_tokens or not doc_tokens:
            return 0.0

        query_set = set(query_tokens)
        doc_set = set(doc_tokens)
        overlap = len(query_set.intersection(doc_set))
        return overlap / max(len(query_set), 1)
    
    def retrieve_by_criterion(self, 
                            query: str, 
                            criterion: str,
                            k_naac: int = 3,
                            k_mvsr: int = 3) -> Tuple[RetrievalResult, RetrievalResult]:
        """
        Retrieve documents relevant to a specific NAAC criterion
        
        Args:
            query: Natural language query
            criterion: NAAC criterion number (e.g., "2") 
            k_naac: Number of NAAC documents to retrieve
            k_mvsr: Number of MVSR documents to retrieve
            
        Returns:
            Tuple of (naac_results, mvsr_results)
        """
        logger.info(f"Retrieving for criterion {criterion}: '{query}'")
        
        # Enhance query with criterion context
        enhanced_query = f"NAAC criterion {criterion}: {query}"
        
        return self.retrieve_compliance_context_hybrid(
            enhanced_query,
            k_naac=k_naac,
            k_mvsr=k_mvsr,
            criterion_filter=criterion
        )
    
    def retrieve_by_category(self, 
                           query: str,
                           category: str,
                           k_naac: int = 3,
                           k_mvsr: int = 5) -> Tuple[RetrievalResult, RetrievalResult]:
        """
        Retrieve documents relevant to a specific MVSR category
        
        Args:
            query: Natural language query 
            category: MVSR category (e.g., "policies", "iqac")
            k_naac: Number of NAAC documents to retrieve
            k_mvsr: Number of MVSR documents to retrieve
            
        Returns:
            Tuple of (naac_results, mvsr_results)
        """
        logger.info(f"Retrieving for category {category}: '{query}'")
        
        return self.retrieve_compliance_context_hybrid(
            query,
            k_naac=k_naac,
            k_mvsr=k_mvsr,
            category_filter=category
        )
    
    def get_similar_requirements(self, 
                               requirement_text: str,
                               k: int = 5) -> RetrievalResult:
        """
        Find similar NAAC requirements to given requirement text
        
        Args:
            requirement_text: NAAC requirement text to find similarities for
            k: Number of similar requirements to retrieve
            
        Returns:
            RetrievalResult with similar NAAC requirements
        """
        return self._retrieve_naac_requirements(requirement_text, k)
    
    def get_supporting_evidence(self, 
                              evidence_description: str,
                              k: int = 5) -> RetrievalResult:
        """
        Find MVSR evidence that supports a given description
        
        Args:
            evidence_description: Description of evidence to find
            k: Number of evidence documents to retrieve
            
        Returns:
            RetrievalResult with supporting MVSR evidence
        """
        return self._retrieve_mvsr_evidence(evidence_description, k)
    
    def hybrid_search(self, 
                     query: str,
                     naac_weight: float = 0.5,
                     mvsr_weight: float = 0.5,
                     total_results: int = 10) -> List[Dict[str, Any]]:
        """
        Perform hybrid search across both collections with weighted results
        
        Args:
            query: Natural language query
            naac_weight: Weight for NAAC results (0-1)
            mvsr_weight: Weight for MVSR results (0-1)
            total_results: Total number of combined results to return
            
        Returns:
            Combined and ranked results from both collections
        """
        # Normalize weights
        total_weight = naac_weight + mvsr_weight
        naac_weight = naac_weight / total_weight
        mvsr_weight = mvsr_weight / total_weight
        
        # Calculate results per collection
        k_naac = int(total_results * naac_weight)
        k_mvsr = int(total_results * mvsr_weight)
        
        # Ensure minimum results from each
        k_naac = max(k_naac, 2)
        k_mvsr = max(k_mvsr, 2)
        
        naac_results, mvsr_results = self.retrieve_compliance_context(
            query, k_naac, k_mvsr
        )
        
        # Combine and rank results
        combined_results = []
        
        # Add NAAC results with weighted scores
        for i, (doc, meta, dist) in enumerate(zip(
            naac_results.documents, 
            naac_results.metadatas,
            naac_results.distances
        )):
            combined_results.append({
                'document': doc,
                'metadata': meta,
                'distance': dist,
                'similarity': 1 - dist,
                'weighted_score': (1 - dist) * naac_weight,
                'source_type': 'naac_requirement',
                'rank_in_source': i + 1
            })
        
        # Add MVSR results with weighted scores  
        for i, (doc, meta, dist) in enumerate(zip(
            mvsr_results.documents,
            mvsr_results.metadatas, 
            mvsr_results.distances
        )):
            combined_results.append({
                'document': doc,
                'metadata': meta, 
                'distance': dist,
                'similarity': 1 - dist,
                'weighted_score': (1 - dist) * mvsr_weight,
                'source_type': 'mvsr_evidence',
                'rank_in_source': i + 1
            })
        
        # Sort by weighted score (highest first)
        combined_results.sort(key=lambda x: x['weighted_score'], reverse=True)
        
        # Return top results
        return combined_results[:total_results]
    
    def get_retrieval_stats(self) -> Dict[str, Any]:
        """Get retrieval statistics and collection information"""
        
        collection_stats = self.chroma_store.get_collection_stats()
        
        return {
            'collection_stats': collection_stats,
            'retrieval_config': {
                'default_k_naac': self.default_k_naac,
                'default_k_mvsr': self.default_k_mvsr,
                'similarity_threshold': self.similarity_threshold
            },
            'available_filters': {
                'naac_criteria': ['1', '2', '3', '4', '5', '6', '7'],
                'mvsr_categories': ['policies', 'iqac', 'governance', 'student_support', 'reports']
            }
        }
