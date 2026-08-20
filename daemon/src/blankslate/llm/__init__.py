"""LLM provider factory."""

from __future__ import annotations

from blankslate.config import LlmConfig
from blankslate.llm.base import LLMError, LLMProvider
from blankslate.llm.ollama import OllamaProvider
from blankslate.llm.openai_compat import OpenAICompatProvider


def build_provider(config: LlmConfig) -> LLMProvider:
    if config.provider == "ollama":
        return OllamaProvider(
            base_url=config.base_url,
            model=config.model,
            timeout_s=config.timeout_s,
        )
    if config.provider in ("openai", "anthropic", "gemini", "openai-compat"):
        return OpenAICompatProvider(
            base_url=config.base_url or "https://api.openai.com/v1",
            model=config.model,
            api_key=config.api_key,
            timeout_s=config.timeout_s,
        )
    raise LLMError(f"unknown LLM provider: {config.provider}")


__all__ = ["LLMError", "LLMProvider", "build_provider"]
