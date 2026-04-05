"""
Groq API client for LLM integration.
"""

from typing import Dict, Any, List, Optional
import logging

from groq import Groq

from .prompt_utils import build_compliance_prompt, parse_compliance_response, format_error_response

logger = logging.getLogger(__name__)


class GroqClient:
    """Client wrapper for Groq-hosted chat models."""

    def __init__(
        self,
        model_name: str = "llama-3.3-70b-versatile",
        api_key: Optional[str] = None,
        timeout: int = 120,
        allow_missing_api_key: bool = False,
    ):
        self.model_name = model_name
        self.api_key = api_key
        self.timeout = timeout
        self.enabled = bool(self.api_key)

        if not self.api_key and not allow_missing_api_key:
            raise ValueError("Groq API key is required. Set GROQ_API_KEY in .env.")

        if not self.api_key:
            self.client = None
            logger.warning(
                "Groq API key is not set. LLM features are disabled until GROQ_API_KEY is configured."
            )
            return

        self.client = Groq(api_key=self.api_key, timeout=self.timeout)
        logger.info("Groq client initialized with model: %s", self.model_name)

    def generate_compliance_response(
        self,
        user_query: str,
        naac_context: List[str],
        mvsr_context: List[str],
        naac_metadata: List[Dict],
        mvsr_metadata: List[Dict],
        memory_context: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        if not self.enabled:
            return format_error_response(
                "Groq API key is not configured. Set GROQ_API_KEY in .env and restart the backend."
            )

        prompt = build_compliance_prompt(
            user_query, naac_context, mvsr_context, naac_metadata, mvsr_metadata, memory_context
        )

        logger.info("\n" + "=" * 50 + "\n[LLM DEBUG] System Context:\n" + "=" * 50)
        logger.info("Query: %s", user_query)
        logger.info("NAAC Chunks: %s", len(naac_context))
        logger.info("MVSR Chunks: %s", len(mvsr_context))
        logger.debug("[LLM DEBUG] Full Prompt sent to Groq:\n%s\n%s", prompt, "=" * 50)

        try:
            response = self.client.chat.completions.create(
                model=self.model_name,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.0,
                max_tokens=1800,
                top_p=1.0,
            )
            generated_text = self._extract_message_content(response)
            structured_response = parse_compliance_response(
                generated_text, naac_metadata, mvsr_metadata
            )
            logger.info("Generated compliance response successfully")
            return structured_response

        except Exception as exc:
            logger.error("Error generating Groq response: %s", exc)
            return format_error_response(str(exc))

    def test_connection(self) -> bool:
        if not self.enabled:
            return False

        try:
            response = self.client.chat.completions.create(
                model=self.model_name,
                messages=[{"role": "user", "content": "Reply exactly with OK."}],
                temperature=0.0,
                max_tokens=5,
                top_p=1.0,
            )
            return bool(self._extract_message_content(response).strip())
        except Exception as exc:
            logger.debug("Groq connectivity test failed: %s", exc)
            return False

    def get_model_info(self) -> Dict[str, Any]:
        return {
            "provider": "groq",
            "model_name": self.model_name,
            "timeout": self.timeout,
            "enabled": self.enabled,
        }

    def _extract_message_content(self, response: Any) -> str:
        choices = getattr(response, "choices", None) or []
        if not choices:
            return ""

        message = getattr(choices[0], "message", None)
        if message is None:
            return ""

        content = getattr(message, "content", None)
        if content is not None:
            return str(content)

        if isinstance(message, dict):
            return str(message.get("content", ""))

        return str(message)