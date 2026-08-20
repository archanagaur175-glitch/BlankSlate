"""Embedding providers for semantic tool routing."""

from __future__ import annotations

import logging

import numpy as np

logger = logging.getLogger(__name__)


def cosine(a: list[float], b: list[float]) -> float:
    va = np.asarray(a, dtype=np.float64)
    vb = np.asarray(b, dtype=np.float64)
    denom = float(np.linalg.norm(va) * np.linalg.norm(vb))
    if denom == 0:
        return 0.0
    return float(np.dot(va, vb)) / denom


class Embedder:
    """Small embedding facade. Ollama is the default backend; fastembed is
    the fallback used only if Ollama cannot be reached."""

    def __init__(
        self,
        provider: str = "ollama",
        model: str = "nomic-embed-text",
        base_url: str = "http://127.0.0.1:11434",
    ) -> None:
        self.provider = provider
        self.model = model
        self.base_url = base_url
        self._impl = self._build()

    def _build(self):
        if self.provider == "ollama":
            from blankslate.llm.ollama import OllamaProvider

            provider = OllamaProvider(base_url=self.base_url, embed_model=self.model)
            return _ProviderEmbedder(provider)
        if self.provider == "fastembed":
            return FastEmbedEmbedder(self.model)
        raise ValueError(f"unknown embeddings provider: {self.provider}")

    async def embed(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        return await self._impl.embed(texts)


class _ProviderEmbedder:
    def __init__(self, provider) -> None:
        self._provider = provider

    async def embed(self, texts: list[str]) -> list[list[float]]:
        return await self._provider.embed(texts)


class FastEmbedEmbedder:
    """fastembed (Apache-2.0) + all-MiniLM-L6-v2 (MIT) fallback."""

    def __init__(self, model: str = "all-MiniLM-L6-v2") -> None:
        self.model = model
        self._model = None

    def _ensure(self):
        if self._model is None:
            from fastembed import TextEmbedding

            self._model = TextEmbedding(model_name=self.model)
        return self._model

    async def embed(self, texts: list[str]) -> list[list[float]]:
        vectors = list(self._ensure().embed(texts))
        return [list(map(float, vec)) for vec in vectors]