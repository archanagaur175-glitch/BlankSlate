"""Tests for tool routing and embeddings."""

import asyncio

from blankslate.router.embeddings import Embedder, cosine
from blankslate.router.tool_router import ToolRouter, ToolSpec


class _FakeEmbedder:
    """Deterministic bag-of-words embedder over a fixed vocabulary."""

    _VOCAB = [
        "set",
        "timer",
        "open",
        "url",
        "search",
        "web",
        "countdown",
        "query",
        "browse",
        "browser",
        "play",
    ]

    async def embed(self, texts: list[str]) -> list[list[float]]:
        return [self._vectorize(text) for text in texts]

    def _vectorize(self, text: str) -> list[float]:
        import re

        tokens = set(re.findall(r"[a-z]+", text.lower()))
        return [1.0 if word in tokens else 0.0 for word in self._VOCAB]


def three_tools() -> list[ToolSpec]:
    return [
        ToolSpec("open_url", "Open a URL in the browser", {}),
        ToolSpec("search_web", "Search the web for a query", {}),
        ToolSpec("set_timer", "Set a countdown timer", {}),
    ]


def test_embedding_router_returns_top_k():
    embedder = _FakeEmbedder()
    router = ToolRouter(strategy="embedding", embedder=embedder, top_k=2)
    tools = three_tools()
    selected = asyncio.run(router.select("search for news about the web", tools))
    assert len(selected) == 2


def test_embedding_router_orders_by_relevance():
    embedder = _FakeEmbedder()
    router = ToolRouter(strategy="embedding", embedder=embedder, top_k=2)
    tools = three_tools()
    selected = asyncio.run(router.select("set a timer for ten minutes", tools))
    assert selected[0].name == "set_timer"


def test_router_returns_all_when_few_tools():
    router = ToolRouter(strategy="embedding", embedder=None, top_k=5)
    tools = three_tools()
    assert asyncio.run(router.select("anything", tools)) == tools


def test_keyword_router():
    router = ToolRouter(strategy="keyword", top_k=2)
    tools = three_tools()
    selected = asyncio.run(router.select("search the web", tools))
    assert "search_web" in [t.name for t in selected]


def test_keyword_router_all_missing():
    router = ToolRouter(strategy="keyword", top_k=2)
    selected = asyncio.run(router.select("play some loud music", three_tools()))
    assert len(selected) == 2


def test_embedding_fallback_on_failure():
    class _BrokenEmbedder:
        async def embed(self, texts):
            raise RuntimeError("ollama down")

    router = ToolRouter(strategy="embedding", embedder=_BrokenEmbedder(), top_k=2)
    selected = asyncio.run(router.select("search the web for the url", three_tools()))
    assert any(t.name in ("open_url", "search_web") for t in selected)


def test_llm_router_selects_names():
    class _FakeLlm:
        async def chat(self, messages, tools=None, temperature=0.3, max_tokens=None):
            from blankslate.llm.base import LLMResult

            return LLMResult(content='{"tools": ["open_url"]}')

    router = ToolRouter(strategy="llm", llm=_FakeLlm(), top_k=2)
    selected = asyncio.run(router.select("open the browser", three_tools()))
    assert [t.name for t in selected] == ["open_url"]


def test_cosine():
    assert abs(cosine([1.0, 0.0], [1.0, 0.0]) - 1.0) < 1e-9
    assert abs(cosine([1.0, 0.0], [0.0, 1.0])) < 1e-9
    assert cosine([0.0, 0.0], [1.0, 0.0]) == 0.0


def test_tool_spec_signature_and_schema():
    spec = ToolSpec("open_url", "Open a URL", {"type": "object", "properties": {}})
    assert "open_url" in spec.signature()
    schema = spec.to_schema()
    assert schema["type"] == "function"
    assert schema["function"]["name"] == "open_url"


def test_embedder_factory_unknown_provider():
    with __import__("pytest").raises(ValueError):
        Embedder(provider="nope")