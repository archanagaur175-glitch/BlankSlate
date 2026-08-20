"""Pre-loop task planner.

Decomposes multi-step requests ("open the report, summarize it, and email it")
into an ordered list of sub-tasks before the tool-calling loop runs. This
measurably improves reliability on small local models. Degrades to a single
step when the LLM is unavailable or the request is simple.
"""

from __future__ import annotations

import logging

from blankslate.llm.base import LLMProvider
from blankslate.util.json import extract_json

logger = logging.getLogger(__name__)

_PLANNER_SYSTEM = """You are a task planner for a local voice assistant with
access to computer tools. Break the user's request into a short ordered list of
concrete, tool-friendly steps. Respond with ONLY JSON:
{"plan": ["step 1", "step 2", ...], "needs_tools": true|false}
Keep the plan to at most 6 steps. If the request is simple enough to answer
directly, return a single step equal to the request."""

_SPLIT_HINTS = (
    r"\s+and\s+then\s+",
    r"\s+then\s+",
    r"\s+after (that|this)\s+",
    r"\s+also\s+",
)


class TaskPlanner:
    def __init__(self, llm: LLMProvider | None) -> None:
        self.llm = llm

    async def plan(self, query: str) -> list[str]:
        query = (query or "").strip()
        if not query:
            return []
        if self.llm is None:
            return self._heuristic_split(query)
        try:
            result = await self.llm.chat(
                messages=[
                    {"role": "system", "content": _PLANNER_SYSTEM},
                    {"role": "user", "content": query},
                ],
                temperature=0.0,
            )
            parsed = extract_json(result.content)
            if parsed is None:
                return [query]
            steps = parsed.get("plan") or []
            if not isinstance(steps, list):
                return [query]
            clean = [str(s).strip() for s in steps if str(s).strip()]
            return clean or [query]
        except Exception as exc:  # noqa: BLE001
            logger.warning("planner LLM failed (%s); using heuristic split", exc)
            return self._heuristic_split(query)

    def _heuristic_split(self, query: str) -> list[str]:
        import re

        parts = [query]
        for hint in _SPLIT_HINTS:
            merged: list[str] = []
            for part in parts:
                segments = [s.strip() for s in re.split(hint, part, maxsplit=2) if s.strip()]
                merged.extend(segments)
            parts = merged
        return parts or [query]
