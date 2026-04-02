"""
Hugging Face Inference API client for LLM integration.
"""

from typing import Dict, Any, List, Optional
import logging

from huggingface_hub import InferenceClient

from .prompt_utils import build_compliance_prompt, parse_compliance_response, format_error_response

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
        memory_context: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        prompt = build_compliance_prompt(
            user_query, naac_context, mvsr_context, naac_metadata, mvsr_metadata, memory_context
        )

        logger.info("\n" + "="*50 + "\n[LLM DEBUG] System Context:\n" + "="*50)
        logger.info(f"Query: {user_query}")
        logger.info(f"NAAC Chunks: {len(naac_context)}")
        logger.info(f"MVSR Chunks: {len(mvsr_context)}")
        logger.info("—" * 50)
        logger.debug(f"[LLM DEBUG] Full Prompt sent to Hugging Face:\n{prompt}\n" + "="*50)

        try:
            # Prefer text-generation; if the endpoint only supports conversational, fall back.
            generated_text = self.client.text_generation(
                prompt,
                max_new_tokens=1800,
                temperature=0.0,
                do_sample=False,
                repetition_penalty=1.12,
                frequency_penalty=0.4,
                seed=42,
                return_full_text=False,
            )

            structured_response = parse_compliance_response(
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
                        max_tokens=1800,
                        temperature=0.0,
                        top_p=0.9,
                        frequency_penalty=0.4,
                        seed=42,
                    )
                    # chat_response.choices[0].message['content'] in HF client
                    generated_text = chat_response.choices[0].message["content"] if chat_response and chat_response.choices else ""
                    structured_response = parse_compliance_response(
                        generated_text, naac_metadata, mvsr_metadata
                    )
                    logger.info("Generated compliance response via chat_completion fallback")
                    return structured_response
                except Exception as chat_err:
                    logger.error(f"Chat completion fallback failed: {chat_err}")
                    return format_error_response(str(chat_err))

            logger.error(f"Error generating Hugging Face response: {e}")
            return format_error_response(str(e))

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
