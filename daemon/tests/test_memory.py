"""Tests for conversation context, history store, and digester."""

import asyncio

from blankslate.config import DaemonConfig
from blankslate.memory.context import ConversationContext
from blankslate.memory.digest import Digester
from blankslate.memory.store import HistoryStore
from blankslate.security.redactor import Redactor


def test_context_bounds_turns():
    ctx = ConversationContext(max_turns=3)
    for i in range(10):
        ctx.add("user", f"q{i}")
        ctx.add("assistant", f"a{i}")
    assert len(ctx) == 3
    assert ctx.as_messages()[-1]["content"] == "a9"


def test_context_messages():
    ctx = ConversationContext(max_turns=4)
    ctx.add_user("hello")
    ctx.add_assistant("hi")
    msgs = ctx.as_messages()
    assert msgs == [
        {"role": "user", "content": "hello", "source": "voice"},
        {"role": "assistant", "content": "hi", "source": "voice"},
    ]


def test_context_recent_text():
    ctx = ConversationContext(max_turns=4)
    ctx.add_user("one")
    ctx.add_assistant("two")
    assert "one" in ctx.recent_text()
    assert "two" in ctx.recent_text()


def test_history_store_roundtrip(tmp_path):
    store = HistoryStore(tmp_path / "hist.db", Redactor(enabled=True))
    store.append("user", "call 555 1212 about the sk_abcdef0123456789 key")
    rows = store.recent(10)
    assert len(rows) == 1
    assert "555 1212" not in rows[0]["content"]
    assert "<redacted_phone>" in rows[0]["content"]
    store.close()


def test_history_store_order(tmp_path):
    store = HistoryStore(tmp_path / "hist.db")
    store.append("user", "first")
    store.append("assistant", "second")
    rows = store.recent(10)
    assert [r["role"] for r in rows] == ["user", "assistant"]
    store.close()


def test_history_store_clear(tmp_path):
    store = HistoryStore(tmp_path / "hist.db")
    store.append("user", "x")
    store.clear()
    assert store.recent(10) == []
    store.close()


def test_digest_truncates_when_no_llm():
    d = Digester(llm=None, enabled=True, max_chars=100)
    text = "a" * 500
    out = asyncio.run(d.digest(text))
    assert len(out) < 500
    assert "..." in out


def test_digest_returns_short_text():
    d = Digester(llm=None, enabled=True)
    assert asyncio.run(d.digest("hi")) == "hi"


class _FakeLlm:
    def __init__(self, reply: str) -> None:
        self.reply = reply

    async def chat(self, messages, tools=None, temperature=0.3, max_tokens=None):
        from blankslate.llm.base import LLMResult

        return LLMResult(content=self.reply)


def test_digest_uses_llm():
    d = Digester(llm=_FakeLlm("short summary"), enabled=True)
    out = asyncio.run(d.digest("some long thing here"))
    assert out == "short summary"


def test_model_config_updates_history_defaults():
    cfg = DaemonConfig()
    assert cfg.context.history_turns == 8
    assert cfg.agents.enabled is True
    assert cfg.mcp.servers == []
