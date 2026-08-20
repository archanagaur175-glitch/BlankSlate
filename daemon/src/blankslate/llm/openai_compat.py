"""OpenAI-compatible provider for optional cloud models.

Only used when the user supplies an API key and explicitly opts in. Never
required: BlankSlate works fully local by default.
"""

from __future__ import annotations

import logging

import httpx

from blankslate.llm.base import LLMError, LLMProvider, LLMResult, LLMToolCall
from blankslate.llm.ollama import _parse_arguments

logger = logging.getLogger(__name__)


class OpenAICompatProvider(LLMProvider):
    name = "openai-compat"

    def __init__(
        self,
        base_url: str,
        model: str,
        api_key: str = "",
        timeout_s: float = 60.0,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.api_key = api_key
        self._client = httpx.AsyncClient(timeout=timeout_s)

    def _headers(self) -> dict:
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        return headers

    async def chat(
        self,
        messages: list[dict],
        tools: list[dict] | None = None,
        temperature: float = 0.3,
        max_tokens: int | None = None,
    ) -> LLMResult:
        payload: dict = {"model": self.model, "messages": messages, "temperature": temperature}
        if tools:
            payload["tools"] = tools
        if max_tokens:
            payload["max_tokens"] = max_tokens
        try:
            resp = await self._client.post(
                f"{self.base_url}/chat/completions",
                json=payload,
                headers=self._headers(),
            )
        except httpx.HTTPError as exc:
            raise LLMError(f"llm request failed: {exc}") from exc
        if resp.status_code != 200:
            raise LLMError(f"llm returned {resp.status_code}: {resp.text[:300]}")
        data = resp.json()
        choice = (data.get("choices") or [{}])[0]
        message = choice.get("message") or {}
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
        raise LLMError("embedding is not supported by the generic provider")

    async def aclose(self) -> None:
        await self._client.aclose()