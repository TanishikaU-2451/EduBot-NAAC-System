"""
RAG Generator Component for NAAC Compliance Intelligence System
Handles response generation using retrieved context and Ollama LLM
"""

from typing import Dict, Any, List, Optional, Tuple
import logging
from dataclasses import dataclass
import json

from ..llm.ollama_client import OllamaClient
from .retriever import RetrievalResult

logger = logging.getLogger(__name__)

@dataclass 
class GenerationContext:
    """Context information for response generation"""
    user_query: str
    naac_results: RetrievalResult
    mvsr_results: RetrievalResult
    additional_context: Optional[Dict[str, Any]] = None

class ComplianceGenerator:
    """
    Generates structured compliance responses using retrieved context
    Specializes in NAAC compliance analysis and MVSR evidence evaluation
    """
    
    def __init__(self, 
                 ollama_client: OllamaClient,
                 max_context_length: int = 8000):
        """
        Initialize the generator
        
        Args:
            ollama_client: Ollama client for LLM interaction
            max_context_length: Maximum context length to send to LLM
        """
        self.ollama_client = ollama_client
        self.max_context_length = max_context_length
    
    def generate_compliance_response(self, 
                                   context: GenerationContext) -> Dict[str, Any]:
        """
        Generate a comprehensive compliance response
        
        Args:
            context: Generation context with query and retrieved results
            
        Returns:
            Structured compliance response
        """
        logger.info(f"Generating compliance response for: '{context.user_query[:100]}...'")
        
        # Prepare context for generation
        naac_context, naac_metadata = self._prepare_naac_context(context.naac_results)
        mvsr_context, mvsr_metadata = self._prepare_mvsr_context(context.mvsr_results)
        
        # Ensure context doesn't exceed limits
        naac_context, mvsr_context = self._truncate_context(
            naac_context, mvsr_context
        )
        
        # Generate response using Ollama
        response = self.ollama_client.generate_compliance_response(
            user_query=context.user_query,
            naac_context=naac_context,
            mvsr_context=mvsr_context,
            naac_metadata=naac_metadata,
            mvsr_metadata=mvsr_metadata
        )
        
        # Enhance response with additional analysis
        enhanced_response = self._enhance_response(
            response, context.naac_results, context.mvsr_results
        )
        
        logger.info("Compliance response generated successfully")
        return enhanced_response
    
    def _prepare_naac_context(self, 
                            naac_results: RetrievalResult) -> Tuple[List[str], List[Dict[str, Any]]]:
        """Prepare NAAC context for generation"""
        
        if not naac_results.documents:
            return [], []
        
        # Sort by similarity (lowest distance first)
        sorted_data = sorted(
            zip(naac_results.documents, naac_results.metadatas, naac_results.distances),
            key=lambda x: x[2]
        )
        
        documents = []
        metadatas = []
        
        for doc, meta, distance in sorted_data:
            # Clean and prepare document text
            cleaned_doc = self._clean_document_text(doc)
            
            if len(cleaned_doc) > 50:  # Skip very short fragments
                documents.append(cleaned_doc)
                
                # Prepare metadata for generation
                prepared_meta = {
                    'criterion': meta.get('criterion', 'N/A'),
                    'indicator': meta.get('indicator', 'N/A'),
                    'version': meta.get('version', 'N/A'),
                    'document_title': meta.get('document_title', 'NAAC Document'),
                    'similarity_score': round(1 - distance, 3)
                }
                metadatas.append(prepared_meta)
        
        logger.debug(f"Prepared {len(documents)} NAAC context documents")
        return documents, metadatas
    
    def _prepare_mvsr_context(self, 
                            mvsr_results: RetrievalResult) -> Tuple[List[str], List[Dict[str, Any]]]:
        """Prepare MVSR context for generation"""
        
        if not mvsr_results.documents:
            return [], []
        
        # Sort by similarity (lowest distance first)
        sorted_data = sorted(
            zip(mvsr_results.documents, mvsr_results.metadatas, mvsr_results.distances),
            key=lambda x: x[2]
        )
        
        documents = []
        metadatas = []
        
        for doc, meta, distance in sorted_data:
            # Clean and prepare document text
            cleaned_doc = self._clean_document_text(doc)
            
            if len(cleaned_doc) > 50:  # Skip very short fragments
                documents.append(cleaned_doc)
                
                # Prepare metadata for generation
                prepared_meta = {
                    'document': meta.get('document_title', meta.get('document', 'MVSR Document')),
                    'year': meta.get('year', 'N/A'),
                    'category': meta.get('category', 'N/A'),
                    'mapped_criterion': meta.get('criterion', 'N/A'),
                    'similarity_score': round(1 - distance, 3)
                }
                metadatas.append(prepared_meta)
        
        logger.debug(f"Prepared {len(documents)} MVSR context documents")
        return documents, metadatas
    
    def _clean_document_text(self, text: str) -> str:
        """Clean and normalize document text for generation"""
        
        # Remove excessive whitespace
        cleaned = ' '.join(text.split())
        
        # Remove page markers and other artifacts  
        import re
        cleaned = re.sub(r'--- Page \d+ ---', '', cleaned)
        cleaned = re.sub(r'--- Table \d+ on Page \d+ ---', '', cleaned)
        
        # Ensure reasonable length
        if len(cleaned) > 1000:
            # Try to find a good break point
            sentences = cleaned.split('.')
            truncated = ''
            for sentence in sentences:
                if len(truncated + sentence) < 900:
                    truncated += sentence + '.'
                else:
                    break
            cleaned = truncated if truncated else cleaned[:900] + '...'
        
        return cleaned.strip()
    
    def _truncate_context(self, 
                        naac_context: List[str], 
                        mvsr_context: List[str]) -> Tuple[List[str], List[str]]:
        """Truncate context to fit within model limits"""
        
        # Calculate current total length
        total_length = sum(len(doc) for doc in naac_context + mvsr_context)
        
        if total_length <= self.max_context_length:
            return naac_context, mvsr_context
        
        # Proportional truncation - preserve balance between NAAC and MVSR
        naac_target = int(self.max_context_length * 0.4)  # 40% for NAAC
        mvsr_target = int(self.max_context_length * 0.4)   # 40% for MVSR (rest for prompt)
        
        # Truncate NAAC context
        truncated_naac = []
        naac_length = 0
        for doc in naac_context:
            if naac_length + len(doc) <= naac_target:
                truncated_naac.append(doc)
                naac_length += len(doc)
            else:
                # Add partial document if it fits
                remaining = naac_target - naac_length
                if remaining > 100:  # Only if meaningful space remains
                    truncated_naac.append(doc[:remaining] + '...')
                break
        
        # Truncate MVSR context
        truncated_mvsr = []
        mvsr_length = 0
        for doc in mvsr_context:
            if mvsr_length + len(doc) <= mvsr_target:
                truncated_mvsr.append(doc)
                mvsr_length += len(doc)
            else:
                # Add partial document if it fits
                remaining = mvsr_target - mvsr_length
                if remaining > 100:  # Only if meaningful space remains
                    truncated_mvsr.append(doc[:remaining] + '...')
                break
        
        logger.debug(f"Truncated context: NAAC {len(naac_context)}->{len(truncated_naac)}, "
                    f"MVSR {len(mvsr_context)}->{len(truncated_mvsr)}")
        
        return truncated_naac, truncated_mvsr
    
    def _enhance_response(self, 
                        base_response: Dict[str, Any],
                        naac_results: RetrievalResult,
                        mvsr_results: RetrievalResult) -> Dict[str, Any]:
        """Enhance the base response with additional analysis"""
        
        enhanced = base_response.copy()
        
        # Add source information
        enhanced['source_analysis'] = {
            'naac_sources_found': len(naac_results.documents),
            'mvsr_sources_found': len(mvsr_results.documents),
            'naac_avg_relevance': self._calculate_avg_relevance(naac_results.distances),
            'mvsr_avg_relevance': self._calculate_avg_relevance(mvsr_results.distances)
        }
        
        # Add confidence score based on source quality
        confidence = self._calculate_confidence_score(
            naac_results, mvsr_results, enhanced
        )
        enhanced['confidence_score'] = confidence
        
        # Add detailed source metadata
        enhanced['detailed_sources'] = {
            'naac_sources': self._format_source_details(naac_results, 'naac'),
            'mvsr_sources': self._format_source_details(mvsr_results, 'mvsr')
        }
        
        # Generate compliance score
        compliance_score = self._generate_compliance_score(enhanced)
        enhanced['compliance_score'] = compliance_score
        
        # Add recommendations enhancement
        if enhanced.get('status') in ['Gap Identified', 'Partially Supported']:
            enhanced['priority_level'] = self._determine_priority_level(enhanced)
            enhanced['implementation_timeline'] = self._suggest_timeline(enhanced)
        
        return enhanced
    
    def _calculate_avg_relevance(self, distances: List[float]) -> float:
        """Calculate average relevance score from distances"""
        if not distances:
            return 0.0
        
        similarities = [1 - dist for dist in distances]
        return round(sum(similarities) / len(similarities), 3)
    
    def _calculate_confidence_score(self, 
                                  naac_results: RetrievalResult,
                                  mvsr_results: RetrievalResult,
                                  response: Dict[str, Any]) -> float:
        """Calculate confidence score for the response"""
        
        factors = []
        
        # Factor 1: Number and quality of sources
        naac_quality = len(naac_results.documents) * self._calculate_avg_relevance(naac_results.distances)
        mvsr_quality = len(mvsr_results.documents) * self._calculate_avg_relevance(mvsr_results.distances)
        source_score = min((naac_quality + mvsr_quality) / 10, 1.0)
        factors.append(source_score * 0.4)
        
        # Factor 2: Response completeness
        completeness = 0.0
        if response.get('naac_requirement') and len(response['naac_requirement']) > 50:
            completeness += 0.25
        if response.get('mvsr_evidence') and len(response['mvsr_evidence']) > 50:
            completeness += 0.25
        if response.get('naac_mapping') and response['naac_mapping'] != "Error in processing":
            completeness += 0.25
        if response.get('compliance_analysis') and len(response['compliance_analysis']) > 100:
            completeness += 0.25
        factors.append(completeness * 0.3)
        
        # Factor 3: Status clarity
        status_clarity = 0.8 if response.get('status') not in ['Processing Error', 'Insufficient Evidence'] else 0.2
        factors.append(status_clarity * 0.3)
        
        confidence = sum(factors)
        return round(confidence, 3)
    
    def _format_source_details(self, 
                             results: RetrievalResult,
                             source_type: str) -> List[Dict[str, Any]]:
        """Format detailed source information"""
        
        sources = []
        for i, (doc, meta, dist) in enumerate(zip(
            results.documents, results.metadatas, results.distances
        )):
            source = {
                'rank': i + 1,
                'relevance_score': round(1 - dist, 3),
                'preview': doc[:150] + '...' if len(doc) > 150 else doc
            }
            
            if source_type == 'naac':
                source.update({
                    'criterion': meta.get('criterion', 'N/A'),
                    'indicator': meta.get('indicator', 'N/A'),
                    'document': meta.get('document_title', 'NAAC Document')
                })
            else:  # mvsr
                source.update({
                    'document': meta.get('document_title', meta.get('document', 'MVSR Document')),
                    'category': meta.get('category', 'N/A'),
                    'year': meta.get('year', 'N/A')
                })
            
            sources.append(source)
        
        return sources
    
    def _generate_compliance_score(self, response: Dict[str, Any]) -> Dict[str, Any]:
        """Generate numerical compliance score"""
        
        status = response.get('status', 'Insufficient Evidence')
        confidence = response.get('confidence_score', 0.0)
        source_count = response.get('context_sources', {})
        
        # Base score from status
        status_scores = {
            'Fully Supported': 0.9,
            'Partially Supported': 0.6,
            'Gap Identified': 0.3,
            'Insufficient Evidence': 0.1,
            'Processing Error': 0.0
        }
        
        base_score = status_scores.get(status, 0.1)
        
        # Adjust based on evidence strength
        naac_sources = source_count.get('naac_sources', 0)
        mvsr_sources = source_count.get('mvsr_sources', 0)
        
        evidence_multiplier = min(1.0, (naac_sources + mvsr_sources) / 8)
        
        # Final score
        final_score = base_score * confidence * evidence_multiplier
        
        return {
            'overall_score': round(final_score, 2),
            'max_score': 1.0,
            'percentage': round(final_score * 100, 1),
            'grade': self._score_to_grade(final_score),
            'components': {
                'status_score': base_score,
                'confidence_factor': confidence,
                'evidence_factor': evidence_multiplier
            }
        }
    
    def _score_to_grade(self, score: float) -> str:
        """Convert numerical score to letter grade"""
        if score >= 0.85:
            return 'A'
        elif score >= 0.70:
            return 'B'  
        elif score >= 0.55:
            return 'C'
        elif score >= 0.40:
            return 'D'
        else:
            return 'F'
    
    def _determine_priority_level(self, response: Dict[str, Any]) -> str:
        """Determine priority level for addressing gaps"""
        
        status = response.get('status', '')
        compliance_score = response.get('compliance_score', {}).get('overall_score', 0)
        
        if status == 'Gap Identified' and compliance_score < 0.3:
            return 'High'
        elif status == 'Partially Supported' and compliance_score < 0.6:
            return 'Medium'
        else:
            return 'Low'
    
    def _suggest_timeline(self, response: Dict[str, Any]) -> str:
        """Suggest implementation timeline based on gap severity"""
        
        priority = response.get('priority_level', 'Low')
        
        timeline_map = {
            'High': 'Immediate (1-3 months)',
            'Medium': 'Short-term (3-6 months)', 
            'Low': 'Long-term (6-12 months)'
        }
        
        return timeline_map.get(priority, 'To be determined')
    
    def generate_summary_response(self, 
                                context: GenerationContext,
                                max_length: int = 500) -> Dict[str, Any]:
        """Generate a concise summary response"""
        
        # Generate full response first
        full_response = self.generate_compliance_response(context)
        
        # Create summary
        summary = {
            'query': context.user_query,
            'status': full_response.get('status', 'Unknown'),
            'key_finding': full_response.get('compliance_analysis', '')[:max_length] + '...',
            'naac_mapping': full_response.get('naac_mapping', 'Not identified'),
            'confidence': full_response.get('confidence_score', 0.0),
            'compliance_grade': full_response.get('compliance_score', {}).get('grade', 'N/A')
        }
        
        return summary