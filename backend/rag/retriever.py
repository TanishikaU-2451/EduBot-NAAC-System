"""
RAG Retriever Component for NAAC Compliance Intelligence System
Handles semantic retrieval from both NAAC requirements and MVSR evidence collections
"""

from typing import List, Dict, Any, Optional, Tuple
import logging
from dataclasses import dataclass

from ..db.chroma_store import ChromaVectorStore

logger = logging.getLogger(__name__)

@dataclass
class RetrievalResult:
    """Structure for retrieval results"""
    documents: List[str]
    metadatas: List[Dict[str, Any]]
    distances: List[float]
    source_type: str  # 'naac_requirement' or 'mvsr_evidence'

class ComplianceRetriever:
    """
    Intelligent retriever for NAAC compliance queries
    Performs semantic retrieval from separated NAAC and MVSR collections
    """
    
    def __init__(self, 
                 chroma_store: ChromaVectorStore,
                 default_k_naac: int = 5,
                 default_k_mvsr: int = 5,
                 similarity_threshold: float = 0.7):
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
            filtered_docs, filtered_metadatas, filtered_distances = self._filter_by_similarity(
                results['documents'],
                results['metadatas'], 
                results['distances']
            )
            
            return RetrievalResult(
                documents=filtered_docs,
                metadatas=filtered_metadatas,
                distances=filtered_distances,
                source_type='naac_requirement'
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
            filtered_docs, filtered_metadatas, filtered_distances = self._filter_by_similarity(
                results['documents'],
                results['metadatas'],
                results['distances']
            )
            
            return RetrievalResult(
                documents=filtered_docs,
                metadatas=filtered_metadatas,
                distances=filtered_distances,
                source_type='mvsr_evidence'
            )
            
        except Exception as e:
            logger.error(f"Error retrieving MVSR evidence: {e}")
            return RetrievalResult([], [], [], 'mvsr_evidence')
    
    def _filter_by_similarity(self, 
                            documents: List[str],
                            metadatas: List[Dict[str, Any]], 
                            distances: List[float]) -> Tuple[List[str], List[Dict[str, Any]], List[float]]:
        """Filter results based on similarity threshold"""
        
        if not documents or not distances:
            return [], [], []
        
        # ChromaDB uses distance (lower is better), convert to similarity
        # Assuming cosine distance: similarity = 1 - distance
        similarities = [1 - dist for dist in distances]
        
        # Filter by threshold
        filtered_docs = []
        filtered_metadatas = [] 
        filtered_distances = []
        
        for i, similarity in enumerate(similarities):
            if similarity >= self.similarity_threshold:
                filtered_docs.append(documents[i])
                filtered_metadatas.append(metadatas[i])
                filtered_distances.append(distances[i])
        
        logger.debug(f"Filtered {len(documents)} -> {len(filtered_docs)} results by similarity threshold")
        
        return filtered_docs, filtered_metadatas, filtered_distances
    
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
        
        return self.retrieve_compliance_context(
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
        
        return self.retrieve_compliance_context(
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