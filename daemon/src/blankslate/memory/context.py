"""Rolling conversational context buffer.

Follow-ups such as "what do you think?" resolve against this buffer without
the user having to repeat the wake word.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class Turn:
    role: str
    content: str
    source: str = "voice"

    def to_dict(self) -> dict:
        return {"role": self.role, "content": self.content, "source": self.source}


class ConversationContext:
    def __init__(self, max_turns: int = 8) -> None:
        self.max_turns = max(1, max_turns)
        self.turns: list[Turn] = []

    def add(self, role: str, content: str, source: str = "voice") -> None:
        if not content:
            return
        self.turns.append(Turn(role=role, content=content, source=source))
        if len(self.turns) > self.max_turns:
            self.turns = self.turns[-self.max_turns :]

    def add_user(self, content: str, source: str = "voice") -> None:
        self.add("user", content, source)

    def add_assistant(self, content: str, source: str = "voice") -> None:
        self.add("assistant", content, source)

    def as_messages(self) -> list[dict]:
        return [turn.to_dict() for turn in self.turns]

    def recent_text(self, limit: int = 4) -> str:
        text = "\n".join(f"{t.role}: {t.content}" for t in self.turns[-limit:])
        return text

    def clear(self) -> None:
        self.turns.clear()

    def __len__(self) -> int:
        return len(self.turns)