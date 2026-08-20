"""Tool router: filters which tools are offered to the main model per query.

Three strategies are selectable:

- ``keyword``: cheap term-matching against tool names + descriptions.
- ``embedding`` (recommended): cosine similarity of query/tool embeddings via
  a small local embedding model; top-K tools are offered so adding more tools
  never degrades latency or accuracy ("zero context rot").
- ``llm``: a small LLM pass picks the relevant tool names.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass

from blankslate.llm.base import LLMProvider
from blankslate.router.embeddings import Embedder, cosine
from blankslate.util.json import extract_json

logger = logging.getLogger(__name__)

_WORD_RE = re.compile(r"[a-z0-9_]+")


@dataclass
class ToolSpec:
    name: str
    description: str
    parameters: dict

    def signature(self) -> str:
        return f"{self.name}: {self.description}"

    def to_schema(self) -> dict:
        from blankslate.llm.base import tool_schema

        return tool_schema(self.name, self.description, self.parameters)


class ToolRouter:
    def __init__(
        self,
        strategy: str = "embedding",
        embedder: Embedder | None = None,
        llm: LLMProvider | None = None,
        top_k: int = 10,
    ) -> None:
        if strategy not in ("keyword", "embedding", "llm"):
            raise ValueError(f"unknown router strategy: {strategy}")
        self.strategy = strategy
        self.embedder = embedder
        self.llm = llm
        self.top_k = max(1, top_k)
        self._tool_vectors: dict[str, list[float]] = {}

    async def select(self, query: str, tools: list[ToolSpec]) -> list[ToolSpec]:
        if not tools:
            return []
        if len(tools) <= self.top_k:
            return tools
        if self.strategy == "keyword":
            return self._keyword(query, tools)
        if self.strategy == "embedding":
            return await self._embedding(query, tools)
        if self.strategy == "llm":
            selected = await self._llm_select(query, tools)
            if selected:
                return selected
            return await self._embedding(query, tools)
        return tools[: self.top_k]

    def _keyword(self, query: str, tools: list[ToolSpec]) -> list[ToolSpec]:
        tokens = set(_WORD_RE.findall((query or "").lower()))
        scored: list[tuple[int, ToolSpec]] = []
        for tool in tools:
            haystack = (tool.name + " " + tool.description).lower()
            score = sum(1 for token in tokens if token in haystack)
            scored.append((score, tool))
        scored.sort(key=lambda item: item[0], reverse=True)
        chosen = [tool for score, tool in scored if score > 0]
        rest = [tool for score, tool in scored if score == 0]
        return (chosen + rest)[: self.top_k]

    async def _embedding(self, query: str, tools: list[ToolSpec]) -> list[ToolSpec]:
        if self.embedder is None:
            return tools[: self.top_k]
        try:
            missing = [t for t in tools if t.name not in self._tool_vectors]
            if missing:
                sigs = [t.signature() for t in missing]
                vectors = await self.embedder.embed(sigs)
                for tool, vec in zip(missing, vectors):
                    self._tool_vectors[tool.name] = vec
            query_vec = (await self.embedder.embed([query]))[0]
            scored = sorted(
                ((cosine(query_vec, self._tool_vectors[t.name]), t) for t in tools),
                key=lambda item: item[0],
                reverse=True,
            )
            return [t for _, t in scored[: self.top_k]]
        except Exception as exc:  # noqa: BLE001
            logger.warning("embedding router failed (%s); falling back to keyword", exc)
            return self._keyword(query, tools)

    async def _llm_select(self, query: str, tools: list[ToolSpec]) -> list[ToolSpec]:
        if self.llm is None:
            return []
        catalog = "\n".join(f"- {t.name}: {t.description}" for t in tools)
        prompt = (
            f"Pick at most {self.top_k} tools from the catalog needed to handle this "
            'request. Respond with ONLY JSON {"tools": ["name1", ...]}. '
            f"Catalog:\n{catalog}\nRequest: {query}"
        )
        try:
            result = await self.llm.chat(
                messages=[
                    {"role": "system", "content": "You select tools. Return only JSON."},
                    {"role": "user", "content": prompt},
                ],
                temperature=0.0,
            )
            parsed = extract_json(result.content)
            if parsed is None:
                return []
            names = parsed.get("tools") or []
            by_name = {t.name: t for t in tools}
            return [by_name[name] for name in names if name in by_name][: self.top_k]
        except Exception as exc:  # noqa: BLE001
            logger.warning("LLM tool routing failed (%s)", exc)
            return []
