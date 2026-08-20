import pytest

from blankslate.app import DaemonApp
from blankslate.config import DaemonConfig


@pytest.fixture
def app() -> DaemonApp:
    return DaemonApp(DaemonConfig())


async def test_ping(app) -> None:
    resp = await app._handle_message({"type": "ping"})
    assert resp == {"type": "pong", "ok": True}


async def test_get_state(app) -> None:
    resp = await app._handle_message({"type": "get_state"})
    assert resp["ok"] is True
    assert resp["type"] == "state"


async def test_set_listening_toggles(app) -> None:
    app.listening = False
    resp = await app._handle_message({"type": "set_listening", "value": True})
    assert resp["ok"] is True
    assert app.listening is True


async def test_unknown_command(app) -> None:
    resp = await app._handle_message({"type": "nonsense"})
    assert resp["ok"] is False
