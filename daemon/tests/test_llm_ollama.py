"""Tests for Ollama provider chat/embed with mocked HTTP."""

import asyncio

import httpx
import pytest

from blankslate.llm.base import LLMError
from blankslate.llm.ollama import OllamaProvider


def _patch_post(provider, status: int, payload: dict):
    async def fake_post(url, **kwargs):
        return httpx.Response(status, json=payload)

    provider._client.post = fake_post


def test_chat_simple_content():
    provider = OllamaProvider()
    _patch_post(provider, 200, {"message": {"content": "Hello!"}})
    result = asyncio.run(provider.chat([{"role": "user", "content": "hi"}]))
    assert result.content == "Hello!"
    assert result.tool_calls == []


def test_chat_with_tool_calls():
    provider = OllamaProvider()
    _patch_post(
        provider,
        200,
        {
            "message": {
                "content": "",
                "tool_calls": [
                    {
                        "id": "call_1",
                        "function": {"name": "open_url", "arguments": {"url": "https://x.dev"}},
                    }
                ],
            }
        },
    )
    result = asyncio.run(provider.chat([{"role": "user", "content": "open the site"}], tools=[{}]))
    assert len(result.tool_calls) == 1
    call = result.tool_calls[0]
    assert call.name == "open_url"
    assert call.arguments == {"url": "https://x.dev"}


def test_chat_string_arguments_parsed():
    provider = OllamaProvider()
    _patch_post(
        provider,
        200,
        {
            "message": {
                "tool_calls": [
                    {
                        "id": "c2",
                        "function": {"name": "search_web", "arguments": '{"query": "cats"}'},
                    }
                ]
            }
        },
    )
    result = asyncio.run(provider.chat([{"role": "user", "content": "search cats"}]))
    assert result.tool_calls[0].arguments == {"query": "cats"}


def test_chat_error_raises_llm_error():
    provider = OllamaProvider()
    _patch_post(provider, 500, {"error": "boom"})
    with pytest.raises(LLMError):
        asyncio.run(provider.chat([{"role": "user", "content": "x"}]))


def test_embed_uses_embed_model():
    provider = OllamaProvider(model="qwen3:4b", embed_model="nomic-embed-text")
    sent = {}

    async def fake_post(url, **kwargs):
        sent["url"] = url
        sent["json"] = kwargs.get("json")
        return httpx.Response(200, json={"embeddings": [[0.1, 0.2]]})

    provider._client.post = fake_post
    vectors = asyncio.run(provider.embed("hello"))
    assert sent["url"].endswith("/api/embed")
    assert sent["json"]["model"] == "nomic-embed-text"
    assert len(vectors) == 1
    assert vectors[0] == [0.1, 0.2]


def test_embed_list_input():
    provider = OllamaProvider()
    sent = {}

    async def fake_post(url, **kwargs):
        sent["json"] = kwargs.get("json")
        return httpx.Response(200, json={"embeddings": [[1.0], [2.0]]})

    provider._client.post = fake_post
    vectors = asyncio.run(provider.embed(["a", "b"]))
    assert sent["json"]["input"] == ["a", "b"]
    assert len(vectors) == 2


def test_ping():
    provider = OllamaProvider()

    async def fake_get(url, **kwargs):
        return httpx.Response(200, json={"version": "0.5.0"})

    provider._client.get = fake_get
    assert asyncio.run(provider.ping()) is True


def test_ping_false_on_error():
    provider = OllamaProvider()
    provider._client.get = None

    async def boom(url, **kwargs):
        raise httpx.ConnectError("refused")

    provider._client.get = boom
    assert asyncio.run(provider.ping()) is False