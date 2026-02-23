"""
Ollama Client for Local LLM Integration
Handles communication with Ollama server running Llama3 model
"""

import ollama
import json
from typing import Dict, Any, Optional, List
import logging
import requests
from pathlib import Path

logger = logging.getLogger(__name__)

class OllamaClient:
    """
    Client for interacting with Ollama local LLM server
    Specialized for NAAC compliance queries and structured responses
    """
    
    def __init__(self, 
                 model_name: str = "llama3",
                 host: str = "http://localhost:11434"):
        """
        Initialize Ollama client
        
        Args:
            model_name: Name of the model to use (default: llama3)
            host: Ollama server host URL
        """
        self.model_name = model_name
        self.host = host
        self.client = ollama.Client(host=host)
        
        # Verify connection and model availability
        self._verify_connection()
    
    def _verify_connection(self):
        """Verify Ollama server is running and model is available"""
        try:
            # Check if server is running
            response = requests.get(f"{self.host}/api/tags")
            if response.status_code != 200:
                raise ConnectionError(f"Cannot connect to Ollama server at {self.host}")
            
            # Check if model is available
            models = response.json().get('models', [])
            available_models = [model['name'] for model in models]
            
            if not any(self.model_name in model for model in available_models):
                logger.warning(f"Model {self.model_name} not found. Available models: {available_models}")
                # Try to pull the model
                self._pull_model()
            
            logger.info(f"Ollama client initialized with model: {self.model_name}")
            
        except Exception as e:
            logger.error(f"Error connecting to Ollama: {e}")
            raise
    
    def _pull_model(self):
        """Pull the specified model if not available"""
        try:
            logger.info(f"Pulling model {self.model_name}...")
            self.client.pull(self.model_name)
            logger.info(f"Model {self.model_name} pulled successfully")
        except Exception as e:
            logger.error(f"Error pulling model {self.model_name}: {e}")
            raise
    
    def generate_compliance_response(self, 
                                   user_query: str,
                                   naac_context: List[str],
                                   mvsr_context: List[str],
                                   naac_metadata: List[Dict],
                                   mvsr_metadata: List[Dict]) -> Dict[str, Any]:
        """
        Generate structured compliance response using retrieved context
        
        Args:
            user_query: Original user question
            naac_context: Retrieved NAAC requirement documents
            mvsr_context: Retrieved MVSR evidence documents
            naac_metadata: Metadata for NAAC documents
            mvsr_metadata: Metadata for MVSR documents
            
        Returns:
            Structured response with NAAC requirements, MVSR evidence, mapping, and status
        """
        
        # Build comprehensive prompt for structured response
        prompt = self._build_compliance_prompt(
            user_query, naac_context, mvsr_context, naac_metadata, mvsr_metadata
        )
        
        try:
            response = self.client.generate(
                model=self.model_name,
                prompt=prompt,
                options={
                    "temperature": 0.1,  # Low temperature for consistent, factual responses
                    "top_p": 0.9,
                    "max_tokens": 2048,
                    "stop": ["</response>"]
                }
            )
            
            # Parse and structure the response
            generated_text = response['response']
            structured_response = self._parse_compliance_response(generated_text, naac_metadata, mvsr_metadata)
            
            logger.info("Generated compliance response successfully")
            return structured_response
            
        except Exception as e:
            logger.error(f"Error generating response: {e}")
            return self._get_error_response(str(e))
    
    def _build_compliance_prompt(self, 
                               user_query: str,
                               naac_context: List[str],
                               mvsr_context: List[str],
                               naac_metadata: List[Dict],
                               mvsr_metadata: List[Dict]) -> str:
        """Build comprehensive prompt for compliance analysis"""
        
        # Format NAAC requirements section
        naac_section = ""
        if naac_context and naac_metadata:
            naac_section = "NAAC REQUIREMENTS:\n"
            for i, (doc, meta) in enumerate(zip(naac_context, naac_metadata)):
                criterion = meta.get('criterion', 'N/A')
                indicator = meta.get('indicator', 'N/A')
                naac_section += f"Criterion {criterion}, Indicator {indicator}:\n{doc}\n\n"
        
        # Format MVSR evidence section
        mvsr_section = ""
        if mvsr_context and mvsr_metadata:
            mvsr_section = "MVSR EVIDENCE:\n"
            for i, (doc, meta) in enumerate(zip(mvsr_context, mvsr_metadata)):
                doc_name = meta.get('document', 'Unknown Document')
                year = meta.get('year', 'N/A')
                mvsr_section += f"{doc_name} ({year}):\n{doc}\n\n"
        
        prompt = f"""You are an expert NAAC compliance analyst for MVSR Engineering College. Analyze the provided information to answer the user's query with precision and structure.

USER QUERY: {user_query}

{naac_section}

{mvsr_section}

INSTRUCTIONS:
1. Provide a comprehensive analysis comparing NAAC requirements with MVSR evidence
2. Be specific about criterion mappings and compliance status
3. Identify gaps or strengths clearly
4. Use only the provided context - do not make assumptions
5. Structure your response as follows:

<response>
<naac_requirement>
[Summarize relevant NAAC requirements from the context]
</naac_requirement>

<mvsr_evidence>
[Summarize relevant MVSR evidence and practices from the context]
</mvsr_evidence>

<naac_mapping>
[Specify the primary NAAC criterion and indicators that apply]
</naac_mapping>

<compliance_analysis>
[Detailed analysis of how MVSR evidence aligns with or gaps from NAAC requirements]
</compliance_analysis>

<status>
[One of: "Fully Supported", "Partially Supported", "Gap Identified", "Insufficient Evidence"]
</status>

<recommendations>
[Specific actionable recommendations if gaps are identified]
</recommendations>
</response>

Generate the response now:"""
        
        return prompt
    
    def _parse_compliance_response(self, 
                                 generated_text: str, 
                                 naac_metadata: List[Dict],
                                 mvsr_metadata: List[Dict]) -> Dict[str, Any]:
        """Parse the generated response into structured format"""
        
        try:
            # Extract sections using tags
            def extract_section(text: str, tag: str) -> str:
                start_tag = f"<{tag}>"
                end_tag = f"</{tag}>"
                start = text.find(start_tag)
                end = text.find(end_tag)
                
                if start != -1 and end != -1:
                    return text[start + len(start_tag):end].strip()
                return ""
            
            naac_requirement = extract_section(generated_text, "naac_requirement")
            mvsr_evidence = extract_section(generated_text, "mvsr_evidence")
            naac_mapping = extract_section(generated_text, "naac_mapping")
            compliance_analysis = extract_section(generated_text, "compliance_analysis")
            status = extract_section(generated_text, "status")
            recommendations = extract_section(generated_text, "recommendations")
            
            # Determine primary criterion from metadata
            primary_criterion = "General"
            if naac_metadata and naac_metadata[0].get('criterion'):
                primary_criterion = f"Criterion {naac_metadata[0]['criterion']}"
                if naac_metadata[0].get('indicator'):
                    primary_criterion += f".{naac_metadata[0]['indicator']}"
            
            return {
                "naac_requirement": naac_requirement,
                "mvsr_evidence": mvsr_evidence,
                "naac_mapping": naac_mapping if naac_mapping else primary_criterion,
                "compliance_analysis": compliance_analysis,
                "status": status if status else "Insufficient Evidence",
                "recommendations": recommendations,
                "query_processed": True,
                "context_sources": {
                    "naac_sources": len(naac_metadata),
                    "mvsr_sources": len(mvsr_metadata)
                }
            }
            
        except Exception as e:
            logger.error(f"Error parsing response: {e}")
            return self._get_error_response(f"Response parsing failed: {e}")
    
    def _get_error_response(self, error_message: str) -> Dict[str, Any]:
        """Return structured error response"""
        return {
            "naac_requirement": "Unable to retrieve NAAC requirements",
            "mvsr_evidence": "Unable to retrieve MVSR evidence",
            "naac_mapping": "Error in processing",
            "compliance_analysis": f"Analysis failed: {error_message}",
            "status": "Processing Error",
            "recommendations": "Please check system configuration and try again",
            "query_processed": False,
            "error": error_message
        }
    
    def test_connection(self) -> bool:
        """Test if Ollama server is responding"""
        try:
            response = self.client.generate(
                model=self.model_name,
                prompt="Hello, respond with 'OK' if you're working.",
                options={"max_tokens": 10}
            )
            return "OK" in response['response'] or len(response['response']) > 0
        except:
            return False
    
    def get_model_info(self) -> Dict[str, Any]:
        """Get information about the current model"""
        try:
            response = requests.get(f"{self.host}/api/show", 
                                  json={"name": self.model_name})
            if response.status_code == 200:
                return response.json()
            return {"error": "Model info not available"}
        except Exception as e:
            return {"error": str(e)}