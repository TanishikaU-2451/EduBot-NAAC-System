"""Backward-compatible import shim for the Groq LLM client."""

from .groq_client import GroqClient, GroqClient as HuggingFaceClient
