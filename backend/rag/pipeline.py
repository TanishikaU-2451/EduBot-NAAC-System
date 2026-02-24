"""
RAG Pipeline for NAAC Compliance Intelligence System
Orchestrates retrieval and generation for complete RAG workflow
"""

from typing import Dict, Any, Optional, List
import logging
import time
from dataclasses import dataclass

from ..db.chroma_store import ChromaVectorStore
from ..llm.ollama_client import OllamaClient
from .retriever import ComplianceRetriever, RetrievalResult
from .generator import ComplianceGenerator, GenerationContext

logger = logging.getLogger(__name__)

@dataclass
class QueryContext:
    """Extended context for query processing"""
    original_query: str
    processed_query: str
    query_type: str  # 'general', 'criterion_specific', 'evidence_lookup', 'gap_analysis'
    suggested_filters: Dict[str, Any]
    confidence_threshold: float

class RAGPipeline:
    """
    Complete RAG pipeline for NAAC compliance intelligence
    Handles query processing, retrieval, generation, and response formatting
    """
    
    def __init__(self, 
                 chroma_store: ChromaVectorStore,
                 ollama_client: OllamaClient,
                 retrieval_config: Optional[Dict[str, Any]] = None):
        """
        Initialize RAG pipeline
        
        Args:
            chroma_store: ChromaDB vector store instance
            ollama_client: Ollama LLM client
            retrieval_config: Configuration for retrieval parameters
        """
        self.chroma_store = chroma_store
        self.ollama_client = ollama_client
        
        # Initialize retriever with custom config
        retrieval_config = retrieval_config or {}
        self.retriever = ComplianceRetriever(
            chroma_store=chroma_store,
            default_k_naac=retrieval_config.get('default_k_naac', 5),
            default_k_mvsr=retrieval_config.get('default_k_mvsr', 5),
            similarity_threshold=retrieval_config.get('similarity_threshold', 0.3)
        )
        
        # Initialize generator
        self.generator = ComplianceGenerator(
            ollama_client=ollama_client,
            max_context_length=retrieval_config.get('max_context_length', 3000)
        )
        
        # Query processing patterns
        self.query_patterns = {
            'criterion_patterns': [
                r'criterion\s*(\d+)', r'key\s*indicator\s*(\d+\.\d+)', 
                r'naac\s*(\d+)', r'standard\s*(\d+)'
            ],
            'category_patterns': {
                'policies': ['policy', 'policies', 'guidelines', 'rules'],
                'iqac': ['iqac', 'quality', 'internal quality', 'quality assurance'],
                'governance': ['governance', 'management', 'leadership', 'administration'],
                'student_support': ['student support', 'student services', 'counseling', 'guidance'],
                'reports': ['report', 'annual report', 'self study', 'ssr']
            },
            'query_types': {
                'gap_analysis': ['gap', 'missing', 'lacking', 'shortfall', 'deficiency'],
                'evidence_lookup': ['evidence', 'proof', 'support', 'documentation'],
                'compliance_check': ['compliant', 'meets', 'satisfies', 'fulfills'],
                'requirements': ['requirement', 'expects', 'mandates', 'standard']
            }
        }
    
    def process_query(self, 
                     user_query: str,
                     context_filters: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        Main query processing pipeline
        
        Args:
            user_query: Natural language query from user
            context_filters: Optional filters for retrieval
            
        Returns:
            Complete structured response
        """
        start_time = time.time()
        
        logger.info(f"Processing query: '{user_query[:100]}...'")
        
        try:
            # Step 1: Analyze and process query
            query_context = self._analyze_query(user_query)
            
            # Step 2: Apply any provided filters
            if context_filters:
                query_context.suggested_filters.update(context_filters)
            
            # Step 3: Retrieve relevant context
            naac_results, mvsr_results = self._retrieve_context(query_context)
            
            # Step 4: Generate response
            generation_context = GenerationContext(
                user_query=user_query,
                naac_results=naac_results,
                mvsr_results=mvsr_results,
                additional_context={'query_analysis': query_context}
            )
            
            response = self.generator.generate_compliance_response(generation_context)
            
            # Step 5: Add pipeline metadata
            processing_time = time.time() - start_time
            response['pipeline_metadata'] = {
                'processing_time_seconds': round(processing_time, 2),
                'query_type': query_context.query_type,
                'filters_applied': query_context.suggested_filters,
                'retrieval_stats': {
                    'naac_documents': len(naac_results.documents),
                    'mvsr_documents': len(mvsr_results.documents)
                }
            }
            
            logger.info(f"Query processed successfully in {processing_time:.2f}s")
            return response
            
        except Exception as e:
            logger.error(f"Error processing query: {e}")
            return self._generate_error_response(user_query, str(e))
    
    def _analyze_query(self, query: str) -> QueryContext:
        """Analyze query to determine type and suggest filters"""
        
        query_lower = query.lower()
        
        # Detect criterion references
        criterion_match = None
        for pattern in self.query_patterns['criterion_patterns']:
            import re
            match = re.search(pattern, query_lower)
            if match:
                criterion_match = match.group(1).split('.')[0]  # Get criterion number
                break
        
        # Detect category references
        category_match = None
        for category, keywords in self.query_patterns['category_patterns'].items():
            if any(keyword in query_lower for keyword in keywords):
                category_match = category
                break
        
        # Determine query type
        query_type = 'general'
        for q_type, keywords in self.query_patterns['query_types'].items():
            if any(keyword in query_lower for keyword in keywords):
                query_type = q_type
                break
        
        # Override if criterion-specific
        if criterion_match:
            query_type = 'criterion_specific'
        
        # Build suggested filters
        suggested_filters = {}
        if criterion_match:
            suggested_filters['criterion_filter'] = criterion_match
        if category_match:
            suggested_filters['category_filter'] = category_match
        
        # Enhance query for better retrieval
        processed_query = self._enhance_query(query, query_type, criterion_match)
        
        return QueryContext(
            original_query=query,
            processed_query=processed_query,
            query_type=query_type,
            suggested_filters=suggested_filters,
            confidence_threshold=0.7
        )
    
    def _enhance_query(self, 
                      original_query: str, 
                      query_type: str,
                      criterion: Optional[str]) -> str:
        """Enhance query for better retrieval"""
        
        enhancements = []
        
        # Add NAAC context
        enhancements.append("NAAC compliance")
        
        # Add criterion context if detected
        if criterion:
            enhancements.append(f"criterion {criterion}")
        
        # Add type-specific context
        type_context = {
            'gap_analysis': "compliance gap analysis requirements",
            'evidence_lookup': "institutional evidence documentation",
            'compliance_check': "NAAC standards compliance verification", 
            'requirements': "NAAC accreditation requirements"
        }
        
        if query_type in type_context:
            enhancements.append(type_context[query_type])
        
        # Combine with original query
        enhanced = f"{original_query} {' '.join(enhancements)}"
        return enhanced.strip()
    
    def _retrieve_context(self, query_context: QueryContext) -> tuple[RetrievalResult, RetrievalResult]:
        """Retrieve context based on query analysis"""
        
        # Determine retrieval strategy
        if query_context.query_type == 'criterion_specific':
            criterion = query_context.suggested_filters.get('criterion_filter')
            if criterion:
                return self.retriever.retrieve_by_criterion(
                    query_context.processed_query,
                    criterion,
                    k_naac=6,  # More NAAC docs for criterion queries
                    k_mvsr=4
                )
        
        elif query_context.query_type == 'evidence_lookup':
            category = query_context.suggested_filters.get('category_filter')
            if category:
                return self.retriever.retrieve_by_category(
                    query_context.processed_query,
                    category,
                    k_naac=3,
                    k_mvsr=7  # More MVSR docs for evidence queries
                )
        
        # Default retrieval
        return self.retriever.retrieve_compliance_context(
            query_context.processed_query,
            criterion_filter=query_context.suggested_filters.get('criterion_filter'),
            category_filter=query_context.suggested_filters.get('category_filter')
        )
    
    def batch_process_queries(self, 
                            queries: List[str],
                            context_filters: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
        """Process multiple queries in batch"""
        
        logger.info(f"Processing {len(queries)} queries in batch")
        
        results = []
        for i, query in enumerate(queries):
            logger.info(f"Processing batch query {i+1}/{len(queries)}")
            
            try:
                result = self.process_query(query, context_filters)
                results.append(result)
            except Exception as e:
                logger.error(f"Error in batch query {i+1}: {e}")
                results.append(self._generate_error_response(query, str(e)))
        
        return results
    
    def get_similar_queries(self, 
                          query: str,
                          k: int = 5) -> List[Dict[str, Any]]:
        """Find similar queries based on NAAC requirements"""
        
        # Use hybrid search to find similar content
        similar_results = self.retriever.hybrid_search(
            query=query,
            naac_weight=0.8,  # Focus on NAAC requirements
            mvsr_weight=0.2,
            total_results=k
        )
        
        # Format as query suggestions
        suggestions = []
        for result in similar_results:
            meta = result['metadata']
            suggestions.append({
                'suggested_query': f"What does NAAC expect for {meta.get('criterion', 'compliance')}?",
                'criterion': meta.get('criterion'),
                'similarity_score': result['similarity'],
                'source_preview': result['document'][:100] + '...'
            })
        
        return suggestions
    
    def explain_compliance_gap(self, 
                             requirement: str,
                             current_evidence: str) -> Dict[str, Any]:
        """Analyze specific compliance gap"""
        
        gap_query = f"""
        Compare NAAC requirement: {requirement}
        Against MVSR current practice: {current_evidence}
        What are the gaps and how to address them?
        """
        
        # Process as gap analysis
        context_filters = {'query_type_override': 'gap_analysis'}
        response = self.process_query(gap_query, context_filters)
        
        # Add specific gap analysis enhancements
        if response.get('status') == 'Gap Identified':
            response['gap_analysis'] = {
                'requirement_summary': requirement[:200] + '...',
                'current_evidence_summary': current_evidence[:200] + '...',
                'specific_gaps': response.get('recommendations', '').split('\n'),
                'severity': response.get('priority_level', 'Medium')
            }
        
        return response
    
    def _generate_error_response(self, query: str, error: str) -> Dict[str, Any]:
        """Generate structured error response"""
        
        return {
            'naac_requirement': 'Unable to retrieve NAAC requirements due to system error',
            'mvsr_evidence': 'Unable to retrieve MVSR evidence due to system error',
            'naac_mapping': 'Error in processing',
            'compliance_analysis': f'Query processing failed: {error}',
            'status': 'Processing Error',
            'recommendations': 'Please check system configuration and try again',
            'query_processed': False,
            'error_details': {
                'original_query': query,
                'error_message': error
            },
            'confidence_score': 0.0
        }
    
    def get_pipeline_health(self) -> Dict[str, Any]:
        """Get health status of all pipeline components"""
        
        health_status = {
            'timestamp': time.time(),
            'overall_status': 'healthy'
        }
        
        # Test ChromaDB
        try:
            stats = self.chroma_store.get_collection_stats()
            health_status['chroma_db'] = {
                'status': 'healthy',
                'collections': stats
            }
        except Exception as e:
            health_status['chroma_db'] = {
                'status': 'error',
                'error': str(e)
            }
            health_status['overall_status'] = 'degraded'
        
        # Test Ollama
        try:
            ollama_test = self.ollama_client.test_connection()
            health_status['ollama'] = {
                'status': 'healthy' if ollama_test else 'error',
                'connection': ollama_test
            }
            if not ollama_test:
                health_status['overall_status'] = 'degraded'
        except Exception as e:
            health_status['ollama'] = {
                'status': 'error',
                'error': str(e)
            }
            health_status['overall_status'] = 'degraded'
        
        # Test retrieval system
        try:
            test_results = self.retriever.retrieve_compliance_context("test query", k_naac=1, k_mvsr=1)
            health_status['retrieval'] = {
                'status': 'healthy',
                'test_retrieval_success': True
            }
        except Exception as e:
            health_status['retrieval'] = {
                'status': 'error', 
                'error': str(e)
            }
            health_status['overall_status'] = 'degraded'
        
        return health_status
    
    def get_pipeline_stats(self) -> Dict[str, Any]:
        """Get comprehensive pipeline statistics"""
        
        return {
            'retrieval_stats': self.retriever.get_retrieval_stats(),
            'vector_store_stats': self.chroma_store.get_collection_stats(),
            'model_info': self.ollama_client.get_model_info(),
            'pipeline_config': {
                'max_context_length': self.generator.max_context_length,
                'similarity_threshold': self.retriever.similarity_threshold,
                'default_k_naac': self.retriever.default_k_naac,
                'default_k_mvsr': self.retriever.default_k_mvsr
            }
        }