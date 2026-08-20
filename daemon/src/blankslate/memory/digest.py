"""Digest/summarization passes.

Compresses memory recall and raw tool output before it reaches the main
model's context. Enabled for local (small) models, off for large/cloud ones.
"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

_SUMMARY_PROMPT = """Summarize the following conversation history into a short
paragraph that preserves the user's intent, important facts, and any pending
requests. Keep it under 100 words.""" 


class Digester:
    def __init__(self, llm=None, enabled: bool = True, max_chars: int = 4000) -> None:
        self.llm = llm
        self.enabled = enabled
        self.max_chars = max(200, max_chars)

    @property
    def available(self) -> bool:
        return self.enabled and self.llm is not None

    def truncate(self, text: str) -> str:
        if len(text) <= self.max_chars:
            return text
        head = text[: int(self.max_chars * 0.6)]
        tail = text[-int(self.max_chars * 0.4) :]
        return f"{head}\n...\n{tail}"

    async def digest(self, text: str) -> str:
        if not text:
            return text
        if not self.available:
            return self.truncate(text)
        try:
            messages = [
                {"role": "system", "content": _SUMMARY_PROMPT},
                {"role": "user", "content": text},
            ]
            result = await self.llm.chat(messages, temperature=0.2)
            summary = result.content.strip()
            return summary or self.truncate(text)
        except Exception as exc:  # noqa: BLE001
            logger.warning("digest failed, truncating instead: %s", exc)
            return self.truncate(text)

    async def compress_recall(self, older: list[dict], recent: list[dict]) -> list[dict]:
        """Collapse ``older`` messages into one summary message when enabled."""
        if not older:
            return recent
        if not self.available:
            return older + recent
        combined = "\n".join(
            f"{m.get('role')}: {m.get('content')}" for m in older
        )
        summary = await self.digest(combined)
        return [{"role": "system", "content": f"Earlier context: {summary}"}] + recent