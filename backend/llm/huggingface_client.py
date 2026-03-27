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
            # Prefer text-generation; if the endpoint only supports conversational, fall back.
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
            # If the endpoint complains about task support, try the chat-completions style API.
            error_text = str(e)
            if "task" in error_text.lower() or "conversational" in error_text.lower():
                try:
                    chat_response = self.client.chat_completion(
                        messages=[{"role": "user", "content": prompt}],
                        max_tokens=700,
                        temperature=0.1,
                        top_p=0.9,
                    )
                    # chat_response.choices[0].message['content'] in HF client
                    generated_text = chat_response.choices[0].message["content"] if chat_response and chat_response.choices else ""
                    structured_response = self._parse_compliance_response(
                        generated_text, naac_metadata, mvsr_metadata
                    )
                    logger.info("Generated compliance response via chat_completion fallback")
                    return structured_response
                except Exception as chat_err:
                    logger.error(f"Chat completion fallback failed: {chat_err}")
                    return self._get_error_response(str(chat_err))

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
            naac_text = naac_context[0]
            context_parts.append(f"NAAC REQUIREMENT CONTEXT:\n{naac_text}")

        if mvsr_context:
            mvsr_text = mvsr_context[0]
            context_parts.append(f"COLLEGE REPORT / EVIDENCE CONTEXT:\n{mvsr_text}")

        context_block = (
            "\n\n".join(context_parts)
            if context_parts
            else "No retrieved context is available. Mark evidence sufficiency as low and avoid unsupported claims."
        )

        naac_meta_summary = ", ".join(
            [f"criterion={m.get('criterion', 'N/A')}, indicator={m.get('indicator', 'N/A')}" for m in naac_metadata[:5]]
        ) or "N/A"
        mvsr_meta_summary = ", ".join(
            [f"doc={m.get('document', 'N/A')}, category={m.get('category', 'N/A')}, year={m.get('year', 'N/A')}" for m in mvsr_metadata[:5]]
        ) or "N/A"

        prompt = f"""You are a NAAC compliance audit assistant.

Primary task:
Verify whether a college/university NAAC report satisfies applicable NAAC requirements.
Identify mistakes, missing evidence, weak claims, or contradictions in the submitted report context.
Provide corrective actions that are specific and practical for accreditation preparation.

Operating rules:
1) Treat NAAC requirement context as normative criteria.
2) Treat college report/evidence context as claims to be validated.
3) Do not assume compliance if evidence is weak or missing.
4) If context is insufficient, explicitly say "Insufficient evidence" and list what must be provided.
5) Prefer precision over verbosity.

User query:
{user_query}

Retrieved metadata snapshot:
- NAAC: {naac_meta_summary}
- College evidence: {mvsr_meta_summary}

Retrieved context:
{context_block}

Audit workflow to follow:
A) Extract the relevant NAAC conditions/checkpoints for this query.
B) Check each condition against available college evidence.
C) Mark each condition as Satisfied / Partially Satisfied / Not Satisfied / Insufficient Evidence.
D) Identify specific mistakes (incorrect, unsupported, missing, contradictory statements).
E) Provide prioritized remediation steps and documentation suggestions.

Return output using ONLY these XML tags and in this order:
<naac_requirement>List concise NAAC conditions/checkpoints being evaluated.</naac_requirement>
<mvsr_evidence>Summarize evidence found in the uploaded college report/evidence relevant to each checkpoint.</mvsr_evidence>
<naac_mapping>Map checkpoints to criterion/indicator and show per-checkpoint status: Satisfied/Partially Satisfied/Not Satisfied/Insufficient Evidence.</naac_mapping>
<compliance_analysis>Explain end-to-end audit judgement, mistakes found, risk level, and confidence caveats.</compliance_analysis>
<status>One of: Fully Supported, Partially Supported, Gap Identified, Insufficient Evidence, Processing Error.</status>
<recommendations>Prioritized corrective actions with what document/proof to add or fix for each gap.</recommendations>
"""

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

            parse_warnings: List[str] = []
            if not naac_requirement:
                parse_warnings.append("Missing <naac_requirement> section in LLM output")
            if not mvsr_evidence:
                parse_warnings.append("Missing <mvsr_evidence> section in LLM output")
            if not naac_mapping:
                parse_warnings.append("Missing <naac_mapping> section in LLM output")
            if not status:
                parse_warnings.append("Missing <status> section in LLM output")
            if not recommendations:
                parse_warnings.append("Missing <recommendations> section in LLM output")

            query_processed = len(parse_warnings) == 0

            return {
                "naac_requirement": naac_requirement,
                "mvsr_evidence": mvsr_evidence,
                "naac_mapping": naac_mapping,
                "compliance_analysis": compliance_analysis,
                "status": status,
                "recommendations": recommendations,
                "query_processed": query_processed,
                "parse_warnings": parse_warnings,
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
            "naac_requirement": "",
            "mvsr_evidence": "",
            "naac_mapping": "",
            "compliance_analysis": f"Analysis failed: {error_message}",
            "status": "Processing Error",
            "recommendations": "",
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
            # If the API call succeeded, connectivity is healthy.
            return response is not None
        except Exception as text_err:
            # Some hosted endpoints only support chat/completions.
            try:
                chat_response = self.client.chat_completion(
                    messages=[{"role": "user", "content": "Reply exactly with OK."}],
                    max_tokens=5,
                    temperature=0.0,
                )
                if not chat_response:
                    return False

                # Be permissive here: successful chat-completion call means provider is reachable.
                if getattr(chat_response, "choices", None):
                    return True
                return True
            except Exception as chat_err:
                logger.debug(
                    "Hugging Face connectivity test failed for both text and chat APIs: text=%s chat=%s",
                    text_err,
                    chat_err,
                )
                return False

    def get_model_info(self) -> Dict[str, Any]:
        return {
            "provider": "huggingface-inference-api",
            "model_name": self.model_name,
            "timeout": self.timeout,
        }
