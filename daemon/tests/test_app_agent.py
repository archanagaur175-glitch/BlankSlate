"""End-to-end wiring tests for the agent inside DaemonApp."""

import asyncio

from blankslate.app import DaemonApp
from blankslate.config import DaemonConfig
from blankslate.nlu.intent import Intent


class _FakeIpc:
    def __init__(self) -> None:
        self.events = []

    async def broadcast(self, event):
        self.events.append(event)


class _FakeHistory:
    def __init__(self) -> None:
        self.turns = []

    def recent(self, limit=20):
        return self.turns[-limit:]

    def append(self, role, content, source="voice"):
        self.turns.append({"role": role, "content": content, "source": source})


class _FakeAgent:
    def __init__(self, reply: str) -> None:
        self.reply = reply
        self.calls = []

    async def handle(self, query, history):
        self.calls.append((query, history))
        return self.reply


class _FakeJudge:
    def __init__(self, intent: Intent) -> None:
        self.intent = intent

    async def judge(self, text):
        return self.intent


class _FakeDigest:
    async def digest(self, text):
        return "[digested]"


class _FakeTts:
    def __init__(self) -> None:
        self.spoken = []

    def speak(self, text):
        self.spoken.append(text)


def _app(config=None) -> DaemonApp:
    app = DaemonApp(config or DaemonConfig())
    app._ipc = _FakeIpc()
    app._history = _FakeHistory()
    app._digest = _FakeDigest()
    app._tts = _FakeTts()
    app._agent_available = True
    return app


def test_route_undirected_skips_agent():
    app = _app()
    app._judge = _FakeJudge(Intent(directed=False, query="", source="heuristic"))
    app._agent = _FakeAgent("should not run")

    async def run():
        await app._route_text("random chit chat", source="voice")

    asyncio.run(run())
    assert app._agent.calls == []


def test_route_directed_runs_agent_and_records_history():
    app = _app()
    app._judge = _FakeJudge(Intent(directed=True, query="what time is it", source="heuristic"))
    agent = _FakeAgent("It is 3 PM.")
    app._agent = agent

    async def run():
        await app._route_text("hey jarvis what time is it", source="voice")

    asyncio.run(run())
    assert agent.calls == [("what time is it", [])]
    roles = [t["role"] for t in app._history.turns]
    assert roles == ["user", "assistant"]
    assert isinstance(app._tts, _FakeTts)
    assert app._tts.spoken == ["It is 3 PM."]


def test_route_agent_unavailable_falls_back_to_echo():
    cfg = DaemonConfig(demo_echo=True)
    app = _app(cfg)
    app._agent_available = False

    async def run():
        await app._route_text("hello there", source="voice")

    asyncio.run(run())
    assert app._tts.spoken == ["hello there"]


def test_route_with_history_context():
    app = _app()
    app._history.turns = [{"role": "user", "content": "old", "source": "voice"}]
    app._judge = _FakeJudge(Intent(directed=True, query="follow up", source="heuristic"))
    agent = _FakeAgent("ok")
    app._agent = agent

    async def run():
        await app._route_text("hey jarvis follow up", source="voice")

    asyncio.run(run())
    query, history = agent.calls[0]
    assert query == "follow up"
    assert history == [{"role": "user", "content": "old"}]