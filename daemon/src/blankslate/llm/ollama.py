"""Ollama-backed provider (native /api/chat plus /api/embed)."""

from __future__ import annotations

import json
import logging

import httpx

from blankslate.llm.base import LLMError, LLMProvider, LLMResult, LLMToolCall
from blankslate.util.json import extract_json

logger = logging.getLogger(__name__)

_CHAT = "/api/chat"
_EMBED = "/api/embed"
_VERSION = "/api/version"


class OllamaProvider(LLMProvider):
    name = "ollama"

    def __init__(
        self,
        base_url: str = "http://127.0.0.1:11434",
        model: str = "qwen3:4b",
        embed_model: str = "nomic-embed-text",
        timeout_s: float = 60.0,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.embed_model = embed_model
        self.timeout_s = timeout_s
        self._client = httpx.AsyncClient(timeout=timeout_s)

    async def ping(self) -> bool:
        try:
            resp = await self._client.get(f"{self.base_url}{_VERSION}")
            return resp.status_code == 200
        except httpx.HTTPError:
            return False

    async def chat(
        self,
        messages: list[dict],
        tools: list[dict] | None = None,
        temperature: float = 0.3,
        max_tokens: int | None = None,
    ) -> LLMResult:
        payload: dict = {
            "model": self.model,
            "messages": messages,
            "stream": False,
            "options": {"temperature": temperature},
        }
        if tools:
            payload["tools"] = tools
        if max_tokens:
            payload["options"]["num_predict"] = max_tokens
        try:
            resp = await self._client.post(f"{self.base_url}{_CHAT}", json=payload)
        except httpx.HTTPError as exc:
            raise LLMError(f"ollama request failed: {exc}") from exc
        if resp.status_code != 200:
            raise LLMError(f"ollama returned {resp.status_code}: {resp.text[:300]}")
        data = resp.json()
        message = data.get("message") or {}
        content = message.get("content") or ""
        tool_calls = [
            LLMToolCall(
                id=call.get("id") or "",
                name=call["function"]["name"],
                arguments=_parse_arguments(call.get("function", {}).get("arguments", {})),
            )
            for call in (message.get("tool_calls") or [])
        ]
        return LLMResult(content=content.strip(), tool_calls=tool_calls)

    async def embed(self, text: str | list[str]) -> list[list[float]]:
        inputs = [text] if isinstance(text, str) else text
        payload = {"model": self.embed_model, "input": inputs}
        try:
            resp = await self._client.post(f"{self.base_url}{_EMBED}", json=payload)
        except httpx.HTTPError as exc:
            raise LLMError(f"ollama embed failed: {exc}") from exc
        if resp.status_code != 200:
            raise LLMError(f"ollama embed returned {resp.status_code}: {resp.text[:300]}")
        data = resp.json()
        embeddings = data.get("embeddings") or []
        return [list(map(float, vec)) for vec in embeddings]

    async def aclose(self) -> None:
        await self._client.aclose()


def _parse_arguments(arguments: object) -> dict:
    if isinstance(arguments, dict):
        return arguments
    if isinstance(arguments, str):
        parsed = extract_json(arguments)
        if parsed is not None:
            return parsed
        try:
            return json.loads(arguments)
        except json.JSONDecodeError:
            return {"raw": arguments}
    return {}
