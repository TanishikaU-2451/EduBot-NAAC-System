"""
Metadata Mapper for NAAC Compliance Intelligence System
Handles dynamic mapping between queries, NAAC criteria, and MVSR evidence categories
"""

import re
from typing import Dict, Any, List, Optional, Tuple
import logging
from dataclasses import dataclass
from collections import defaultdict

logger = logging.getLogger(__name__)

@dataclass
class CriterionMapping:
    """Structure for NAAC criterion mapping"""
    criterion_id: str
    criterion_name: str
    key_indicators: List[str]
    keywords: List[str]
    related_mvsr_categories: List[str]

@dataclass
class QueryMapping:
    """Structure for query to criterion mapping"""
    detected_criteria: List[str]
    suggested_categories: List[str]
    confidence_score: float
    mapping_reasoning: str

class NAACMetadataMapper:
    """
    Dynamic mapper for NAAC criteria and MVSR evidence categories
    Uses semantic analysis to map queries to appropriate criteria without hardcoding
    """
    
    def __init__(self):
        """Initialize metadata mapper with NAAC framework knowledge"""
        
        # NAAC Criteria Framework (2025)
        self.criteria_framework = {
            '1': CriterionMapping(
                criterion_id='1',
                criterion_name='Curricular Aspects',
                key_indicators=['1.1.1', '1.2.1', '1.3.1', '1.4.1'],
                keywords=[
                    'curriculum', 'syllabus', 'course', 'academic program', 'degree program',
                    'curriculum design', 'curriculum development', 'curriculum delivery',
                    'academic calendar', 'course outcomes', 'program outcomes',
                    'choice based credit system', 'cbcs', 'credit system', 'flexible curriculum'
                ],
                related_mvsr_categories=['policies', 'iqac', 'reports']
            ),
            '2': CriterionMapping(
                criterion_id='2', 
                criterion_name='Teaching-Learning and Evaluation',
                key_indicators=['2.1.1', '2.2.1', '2.3.1', '2.4.1', '2.5.1', '2.6.1'],
                keywords=[
                    'teaching', 'learning', 'faculty', 'teacher', 'professor', 'evaluation',
                    'assessment', 'examination', 'student teacher ratio', 'mentoring',
                    'pedagogy', 'teaching methods', 'learning outcomes', 'continuous assessment',
                    'internal assessment', 'innovative teaching', 'blended learning', 'online learning'
                ],
                related_mvsr_categories=['policies', 'iqac', 'governance', 'reports']
            ),
            '3': CriterionMapping(
                criterion_id='3',
                criterion_name='Research, Innovations and Extension',
                key_indicators=['3.1.1', '3.2.1', '3.3.1', '3.4.1', '3.5.1'],
                keywords=[
                    'research', 'innovation', 'extension', 'consultancy', 'publication',
                    'research projects', 'funded research', 'research publications',
                    'patent', 'intellectual property', 'research facilities', 'research culture',
                    'community engagement', 'extension activities', 'outreach programs'
                ],
                related_mvsr_categories=['policies', 'iqac', 'reports']
            ),
            '4': CriterionMapping(
                criterion_id='4',
                criterion_name='Infrastructure and Learning Resources',
                key_indicators=['4.1.1', '4.2.1', '4.3.1', '4.4.1'],
                keywords=[
                    'infrastructure', 'facilities', 'library', 'laboratory', 'equipment',
                    'ict', 'technology', 'campus', 'building', 'classrooms', 'labs',
                    'learning resources', 'digital resources', 'library resources',
                    'physical infrastructure', 'maintenance', 'safety', 'security'
                ],
                related_mvsr_categories=['policies', 'iqac', 'governance', 'reports']
            ),
            '5': CriterionMapping(
                criterion_id='5',
                criterion_name='Student Support and Progression',
                key_indicators=['5.1.1', '5.2.1', '5.3.1', '5.4.1'],
                keywords=[
                    'student support', 'student services', 'counseling', 'guidance', 
                    'placement', 'career guidance', 'alumni', 'student progression',
                    'scholarships', 'financial aid', 'student welfare', 'grievance redressal',
                    'counseling services', 'soft skills', 'personality development'
                ],
                related_mvsr_categories=['student_support', 'policies', 'iqac', 'reports']
            ),
            '6': CriterionMapping(
                criterion_id='6',
                criterion_name='Governance, Leadership and Management',
                key_indicators=['6.1.1', '6.2.1', '6.3.1', '6.4.1', '6.5.1'],
                keywords=[
                    'governance', 'leadership', 'management', 'administration', 'policy',
                    'strategic planning', 'institutional planning', 'quality assurance',
                    'quality policy', 'organizational structure', 'decision making',
                    'financial management', 'internal quality assurance', 'iqac'
                ],
                related_mvsr_categories=['governance', 'policies', 'iqac', 'reports']
            ),
            '7': CriterionMapping(
                criterion_id='7',
                criterion_name='Institutional Values and Best Practices',
                key_indicators=['7.1.1', '7.2.1', '7.3.1'],
                keywords=[
                    'institutional values', 'best practices', 'innovation', 'sustainability',
                    'green practices', 'environmental consciousness', 'social responsibility',
                    'gender equity', 'inclusivity', 'diversity', 'institutional distinctiveness',
                    'core values', 'ethical practices', 'human values'
                ],
                related_mvsr_categories=['policies', 'iqac', 'governance', 'reports']
            )
        }
        
        # MVSR Evidence Categories
        self.mvsr_categories = {
            'policies': [
                'policy', 'policies', 'guidelines', 'rules', 'regulations', 'procedures',
                'code of conduct', 'anti-ragging', 'sexual harassment', 'grievance'
            ],
            'iqac': [
                'iqac', 'internal quality', 'quality assurance', 'quality policy',
                'academic audit', 'quality enhancement', 'continuous improvement',
                'quality initiatives', 'quality indicators', 'quality manual'
            ],
            'governance': [
                'governance', 'management', 'leadership', 'administration', 'board',
                'governing body', 'academic council', 'finance committee',
                'organizational structure', 'strategic planning', 'institutional planning'
            ],
            'student_support': [
                'student support', 'student services', 'counseling', 'guidance',
                'placement', 'career services', 'alumni', 'scholarships', 'welfare',
                'grievance redressal', 'mentoring', 'soft skills development'
            ],
            'reports': [
                'report', 'annual report', 'self study report', 'ssr', 'aqar',
                'institutional report', 'compliance report', 'audit report',
                'assessment report', 'evaluation report', 'progress report'
            ]
        }
        
        # Compile keyword patterns for efficient matching
        self._compile_patterns()
    
    def _compile_patterns(self):
        """Compile regex patterns for keyword matching"""
        
        self.criterion_patterns = {}
        for criterion_id, mapping in self.criteria_framework.items():
            # Create pattern that matches any keyword
            keywords_pattern = '|'.join(re.escape(keyword) for keyword in mapping.keywords)
            self.criterion_patterns[criterion_id] = re.compile(
                f'\\b({keywords_pattern})\\b', 
                re.IGNORECASE
            )
        
        self.category_patterns = {}
        for category, keywords in self.mvsr_categories.items():
            keywords_pattern = '|'.join(re.escape(keyword) for keyword in keywords)
            self.category_patterns[category] = re.compile(
                f'\\b({keywords_pattern})\\b',
                re.IGNORECASE
            )
    
    def map_query_to_criteria(self, query: str) -> QueryMapping:
        """
        Map a query to relevant NAAC criteria and MVSR categories
        
        Args:
            query: Natural language query
            
        Returns:
            QueryMapping with detected criteria and categories
        """
        query_lower = query.lower()
        
        # Score each criterion based on keyword matches
        criterion_scores = {}
        criterion_matches = defaultdict(list)
        
        for criterion_id, pattern in self.criterion_patterns.items():
            matches = pattern.findall(query_lower)
            if matches:
                # Score based on number and uniqueness of matches
                unique_matches = set(matches)
                score = len(unique_matches) * 2 + len(matches)  # Bonus for unique keywords
                criterion_scores[criterion_id] = score
                criterion_matches[criterion_id] = list(unique_matches)
        
        # Score MVSR categories
        category_scores = {}
        category_matches = defaultdict(list)
        
        for category, pattern in self.category_patterns.items():
            matches = pattern.findall(query_lower)
            if matches:
                unique_matches = set(matches)
                score = len(unique_matches) * 2 + len(matches)
                category_scores[category] = score
                category_matches[category] = list(unique_matches)
        
        # Select top criteria and categories
        detected_criteria = self._select_top_criteria(criterion_scores, criterion_matches)
        suggested_categories = self._select_top_categories(category_scores, category_matches)
        
        # Calculate overall confidence
        confidence = self._calculate_mapping_confidence(
            criterion_scores, category_scores, query
        )
        
        # Generate reasoning
        reasoning = self._generate_mapping_reasoning(
            detected_criteria, suggested_categories, 
            criterion_matches, category_matches
        )
        
        return QueryMapping(
            detected_criteria=detected_criteria,
            suggested_categories=suggested_categories,
            confidence_score=confidence,
            mapping_reasoning=reasoning
        )
    
    def _select_top_criteria(self, 
                           scores: Dict[str, float],
                           matches: Dict[str, List[str]]) -> List[str]:
        """Select top criteria based on scores"""
        
        if not scores:
            return []
        
        # Sort by score, take top criteria
        sorted_criteria = sorted(scores.items(), key=lambda x: x[1], reverse=True)
        
        # Take criteria with score > 1 and at least close to top score
        top_score = sorted_criteria[0][1]
        threshold = max(1, top_score * 0.6)
        
        selected = [criterion for criterion, score in sorted_criteria if score >= threshold]
        
        # Limit to top 3
        return selected[:3]
    
    def _select_top_categories(self, 
                             scores: Dict[str, float],
                             matches: Dict[str, List[str]]) -> List[str]:
        """Select top MVSR categories based on scores"""
        
        if not scores:
            return []
        
        sorted_categories = sorted(scores.items(), key=lambda x: x[1], reverse=True)
        
        # Take categories with significant scores
        top_score = sorted_categories[0][1]
        threshold = max(1, top_score * 0.5)
        
        selected = [category for category, score in sorted_categories if score >= threshold]
        
        # Limit to top 2  
        return selected[:2]
    
    def _calculate_mapping_confidence(self, 
                                    criterion_scores: Dict[str, float],
                                    category_scores: Dict[str, float],
                                    query: str) -> float:
        """Calculate confidence score for the mapping"""
        
        factors = []
        
        # Factor 1: Strength of criterion matches
        if criterion_scores:
            max_criterion_score = max(criterion_scores.values())
            criterion_factor = min(max_criterion_score / 10, 1.0)
        else:
            criterion_factor = 0.0
        factors.append(criterion_factor * 0.5)
        
        # Factor 2: Strength of category matches  
        if category_scores:
            max_category_score = max(category_scores.values())
            category_factor = min(max_category_score / 5, 1.0)
        else:
            category_factor = 0.0
        factors.append(category_factor * 0.3)
        
        # Factor 3: Query specificity (longer, more specific queries get higher confidence)
        specificity_factor = min(len(query.split()) / 15, 1.0)
        factors.append(specificity_factor * 0.2)
        
        confidence = sum(factors)
        return round(confidence, 3)
    
    def _generate_mapping_reasoning(self, 
                                  criteria: List[str],
                                  categories: List[str],
                                  criterion_matches: Dict[str, List[str]],
                                  category_matches: Dict[str, List[str]]) -> str:
        """Generate human-readable reasoning for the mapping"""
        
        reasoning_parts = []
        
        if criteria:
            criterion_names = [self.criteria_framework[c].criterion_name for c in criteria]
            reasoning_parts.append(f"Mapped to NAAC Criteria: {', '.join(criterion_names)}")
            
            # Add specific keyword matches
            for criterion in criteria[:2]:  # Show detail for top 2
                matches = criterion_matches.get(criterion, [])
                if matches:
                    criterion_name = self.criteria_framework[criterion].criterion_name
                    reasoning_parts.append(
                        f"Criterion {criterion} ({criterion_name}) - matched keywords: {', '.join(matches[:3])}"
                    )
        
        if categories:
            category_names = [cat.replace('_', ' ').title() for cat in categories]
            reasoning_parts.append(f"MVSR categories: {', '.join(category_names)}")
        
        if not criteria and not categories:
            reasoning_parts.append("No specific criteria detected - using general compliance analysis")
        
        return '. '.join(reasoning_parts)
    
    def get_criterion_details(self, criterion_id: str) -> Optional[Dict[str, Any]]:
        """Get detailed information about a specific criterion"""
        
        if criterion_id not in self.criteria_framework:
            return None
        
        mapping = self.criteria_framework[criterion_id]
        
        return {
            'criterion_id': mapping.criterion_id,
            'criterion_name': mapping.criterion_name,
            'key_indicators': mapping.key_indicators,
            'keywords': mapping.keywords,
            'related_mvsr_categories': mapping.related_mvsr_categories,
            'description': f"NAAC Criterion {mapping.criterion_id}: {mapping.criterion_name}"
        }
    
    def get_category_details(self, category: str) -> Optional[Dict[str, Any]]:
        """Get detailed information about an MVSR category"""
        
        if category not in self.mvsr_categories:
            return None
        
        return {
            'category_name': category,
            'display_name': category.replace('_', ' ').title(),
            'keywords': self.mvsr_categories[category],
            'description': f"MVSR {category.replace('_', ' ').title()} documents and evidence"
        }
    
    def suggest_related_queries(self, 
                              criterion_id: str,
                              limit: int = 5) -> List[str]:
        """Suggest related queries for a given criterion"""
        
        if criterion_id not in self.criteria_framework:
            return []
        
        mapping = self.criteria_framework[criterion_id]
        
        # Generate query templates based on criterion
        templates = [
            f"What does NAAC expect for {mapping.criterion_name.lower()}?",
            f"How does MVSR address {mapping.criterion_name.lower()} requirements?",
            f"What evidence supports NAAC Criterion {criterion_id}?",
            f"Are there gaps in {mapping.criterion_name.lower()} implementation?",
            f"What are the key indicators for Criterion {criterion_id}?"
        ]
        
        # Add keyword-based queries
        for keyword in mapping.keywords[:3]:
            templates.append(f"How does MVSR handle {keyword}?")
        
        return templates[:limit]
    
    def get_comprehensive_mapping(self, query: str) -> Dict[str, Any]:
        """Get comprehensive mapping analysis for a query"""
        
        mapping = self.map_query_to_criteria(query)
        
        # Get detailed information for detected criteria
        criteria_details = []
        for criterion_id in mapping.detected_criteria:
            details = self.get_criterion_details(criterion_id)
            if details:
                criteria_details.append(details)
        
        # Get detailed information for suggested categories
        category_details = []
        for category in mapping.suggested_categories:
            details = self.get_category_details(category)
            if details:
                category_details.append(details)
        
        return {
            'query': query,
            'mapping_results': mapping,
            'criteria_details': criteria_details,
            'category_details': category_details,
            'suggestions': {
                'related_queries': self.suggest_related_queries(mapping.detected_criteria[0]) if mapping.detected_criteria else [],
                'all_criteria': list(self.criteria_framework.keys()),
                'all_categories': list(self.mvsr_categories.keys())
            }
        }