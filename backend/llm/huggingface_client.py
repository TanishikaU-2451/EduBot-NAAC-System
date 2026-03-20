"""
Hugging Face Inference API client for LLM integration.
"""

from typing import Dict, Any, List, Optional
import logging

from huggingface_hub import InferenceClient

logger = logging.getLogger(__name__)


class HuggingFaceClient:
    """Client wrapper for Hugging Face hosted inference models."""

    def __init__(
        self,
        model_name: str = "meta-llama/Meta-Llama-3.1-8B-Instruct",
        api_token: Optional[str] = None,
        timeout: int = 120,
    ):
        self.model_name = model_name
        self.api_token = api_token
        self.timeout = timeout

        if not self.api_token:
            raise ValueError("Hugging Face API token is required. Set HF_API_TOKEN in .env.")

        self.client = InferenceClient(model=self.model_name, token=self.api_token, timeout=self.timeout)
        logger.info(f"Hugging Face client initialized with model: {self.model_name}")

    def generate_compliance_response(
        self,
        user_query: str,
        naac_context: List[str],
        mvsr_context: List[str],
        naac_metadata: List[Dict],
        mvsr_metadata: List[Dict],
    ) -> Dict[str, Any]:
        prompt = self._build_compliance_prompt(
            user_query, naac_context, mvsr_context, naac_metadata, mvsr_metadata
        )

        try:
            generated_text = self.client.text_generation(
                prompt,
                max_new_tokens=700,
                temperature=0.1,
                top_p=0.9,
                do_sample=True,
                return_full_text=False,
            )

            structured_response = self._parse_compliance_response(
                generated_text, naac_metadata, mvsr_metadata
            )

            logger.info("Generated compliance response successfully")
            return structured_response

        except Exception as e:
            logger.error(f"Error generating Hugging Face response: {e}")
            return self._get_error_response(str(e))

    def _build_compliance_prompt(
        self,
        user_query: str,
        naac_context: List[str],
        mvsr_context: List[str],
        naac_metadata: List[Dict],
        mvsr_metadata: List[Dict],
    ) -> str:
        context_parts = []

        if naac_context:
            naac_text = "\n".join(naac_context[:2])[:1500]
            context_parts.append(f"NAAC Requirements:\n{naac_text}")

        if mvsr_context:
            mvsr_text = "\n".join(mvsr_context[:2])[:1500]
            context_parts.append(f"MVSR Evidence:\n{mvsr_text}")

        context_block = (
            "\n\n".join(context_parts)
            if context_parts
            else "No specific context retrieved. Answer based on general NAAC knowledge."
        )

        prompt = f"""You are an expert NAAC compliance assistant for MVSR Engineering College (Maturi Venkata Subba Rao Engineering College).

Question: {user_query}

Context:
{context_block}

Answer the question concisely. Cover: relevant NAAC requirements, MVSR evidence/practices, compliance status, and recommendations if needed. Be factual and specific.

Answer:"""

        return prompt

    def _parse_compliance_response(
        self,
        generated_text: str,
        naac_metadata: List[Dict],
        mvsr_metadata: List[Dict],
    ) -> Dict[str, Any]:
        try:
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

            if not compliance_analysis and generated_text.strip():
                compliance_analysis = generated_text.strip()

            if not naac_requirement and naac_metadata:
                naac_requirement = f"NAAC context retrieved from {len(naac_metadata)} source(s)."

            if not mvsr_evidence and mvsr_metadata:
                mvsr_evidence = f"MVSR evidence retrieved from {len(mvsr_metadata)} source(s)."

            primary_criterion = "General"
            if naac_metadata and naac_metadata[0].get("criterion"):
                primary_criterion = f"Criterion {naac_metadata[0]['criterion']}"
                if naac_metadata[0].get("indicator"):
                    primary_criterion += f".{naac_metadata[0]['indicator']}"

            if not status:
                text_lower = generated_text.lower()
                if any(w in text_lower for w in ["gap", "missing", "lacking", "deficien"]):
                    status = "Gap Identified"
                elif any(w in text_lower for w in ["partial", "partially", "some areas"]):
                    status = "Partially Supported"
                elif any(w in text_lower for w in ["fully", "meets", "satisfies", "compliant"]):
                    status = "Fully Supported"
                else:
                    status = "Partially Supported"

            return {
                "naac_requirement": naac_requirement,
                "mvsr_evidence": mvsr_evidence,
                "naac_mapping": naac_mapping if naac_mapping else primary_criterion,
                "compliance_analysis": compliance_analysis,
                "status": status,
                "recommendations": recommendations,
                "query_processed": True,
                "context_sources": {
                    "naac_sources": len(naac_metadata),
                    "mvsr_sources": len(mvsr_metadata),
                },
            }

        except Exception as e:
            logger.error(f"Error parsing response: {e}")
            return self._get_error_response(f"Response parsing failed: {e}")

    def _get_error_response(self, error_message: str) -> Dict[str, Any]:
        return {
            "naac_requirement": "Unable to retrieve NAAC requirements",
            "mvsr_evidence": "Unable to retrieve MVSR evidence",
            "naac_mapping": "Error in processing",
            "compliance_analysis": f"Analysis failed: {error_message}",
            "status": "Processing Error",
            "recommendations": "Please check system configuration and try again",
            "query_processed": False,
            "error": error_message,
        }

    def test_connection(self) -> bool:
        try:
            response = self.client.text_generation(
                "Reply exactly with OK.",
                max_new_tokens=5,
                temperature=0.0,
                do_sample=False,
                return_full_text=False,
            )
            return len(str(response).strip()) > 0
        except Exception:
            return False

    def get_model_info(self) -> Dict[str, Any]:
        return {
            "provider": "huggingface-inference-api",
            "model_name": self.model_name,
            "timeout": self.timeout,
        }
