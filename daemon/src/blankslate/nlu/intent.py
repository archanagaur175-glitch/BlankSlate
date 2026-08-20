"""Intent judge: directed-vs-ambient classification + wake-word stripping.

The wake word may appear anywhere in an utterance (start, middle, or end).
This pass decides whether speech was *directed at the assistant*, removes the
wake word, and extracts a clean query. It can also use the LLM for robustness,
falling back to deterministic heuristics when the model is unavailable.
"""

from __future__ import annotations

import logging
import re

from blankslate.llm.base import LLMProvider
from blankslate.util.json import extract_json

logger = logging.getLogger(__name__)

_JUDGE_SYSTEM = """You are the wake-word gate for a voice assistant named
BlankSlate. A user utterance was captured around the wake word. Determine
whether the user was speaking directly to the assistant or simply talking to
someone else in the room. Respond with ONLY a JSON object of the form
{"directed": true|false, "query": "the clean request without any wake word"}.
If directed is false, query should be empty."""


class Intent:
    def __init__(self, directed: bool, query: str, source: str = "llm") -> None:
        self.directed = directed
        self.query = query
        self.source = source

    def to_dict(self) -> dict:
        return {"directed": self.directed, "query": self.query, "source": self.source}


def _strip_wake_word(text: str, wake_words: list[str]) -> str:
    out = text
    for word in wake_words:
        pattern = re.compile(re.escape(word), re.IGNORECASE)
        out = pattern.sub("", out, count=1)
    out = re.sub(r"^\s*[:,.\-]?\s*", "", out)
    out = re.sub(r"\s+", " ", out).strip(" .,-")
    return out


def heuristic_judge(text: str, wake_words: list[str]) -> Intent:
    lowered = text.lower()
    if not any(word.lower() in lowered for word in wake_words):
        return Intent(directed=False, query="", source="heuristic")
    query = _strip_wake_word(text, wake_words)
    return Intent(directed=True, query=query, source="heuristic")


class IntentJudge:
    def __init__(self, llm: LLMProvider | None, wake_words: list[str]) -> None:
        self.llm = llm
        self.wake_words = wake_words

    async def judge(self, text: str, context: str = "") -> Intent:
        text = (text or "").strip()
        if not text:
            return Intent(directed=False, query="", source="empty")

        if self.llm is None:
            return heuristic_judge(text, self.wake_words)

        try:
            prompt = (
                f"Wake words: {', '.join(self.wake_words)}\n"
                f"Recent context:\n{context}\n"
                f"Utterance: {text}"
            )
            result = await self.llm.chat(
                messages=[
                    {"role": "system", "content": _JUDGE_SYSTEM},
                    {"role": "user", "content": prompt},
                ],
                temperature=0.0,
            )
            parsed = extract_json(result.content)
            if parsed is None:
                return heuristic_judge(text, self.wake_words)
            directed = bool(parsed.get("directed"))
            query = str(parsed.get("query") or "").strip() if directed else ""
            return Intent(directed=directed, query=query, source="llm")
        except Exception as exc:  # noqa: BLE001
            logger.warning("intent judge LLM failed (%s); using heuristic", exc)
            return heuristic_judge(text, self.wake_words)
