"""LLM provider abstraction."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field


@dataclass
class LLMToolCall:
    id: str
    name: str
    arguments: dict = field(default_factory=dict)


@dataclass
class LLMResult:
    content: str = ""
    tool_calls: list[LLMToolCall] = field(default_factory=list)


class LLMError(RuntimeError):
    pass


class LLMProvider(ABC):
    name: str = "abstract"

    @abstractmethod
    async def chat(
        self,
        messages: list[dict],
        tools: list[dict] | None = None,
        temperature: float = 0.3,
        max_tokens: int | None = None,
    ) -> LLMResult:
        """Return the assistant turn (content and/or tool calls)."""

    @abstractmethod
    async def embed(self, text: str | list[str]) -> list[list[float]]:
        """Embed one or several texts as dense vectors."""

    async def aclose(self) -> None:
        pass


def tool_schema(name: str, description: str, parameters: dict) -> dict:
    return {
        "type": "function",
        "function": {
            "name": name,
            "description": description,
            "parameters": parameters,
        },
    }
