"""Tests for push-to-talk, wake toggle and dictation wiring in DaemonApp."""

import asyncio

import numpy as np

from blankslate.app import DaemonApp
from blankslate.config import DaemonConfig
from blankslate.input.hotkey import HotkeyManager


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


def _app(config=None) -> DaemonApp:
    app = DaemonApp(config or DaemonConfig())
    app._ipc = _FakeIpc()
    app._history = _FakeHistory()
    app._agent_available = False
    return app


class _FakeStt:
    name = "fake"

    def __init__(self, text: str) -> None:
        self.text = text
        self.calls = 0

    def transcribe(self, audio, language=None):
        self.calls += 1
        return self.text


# --------------------------------------------------------------------- hotkey


class _FakeKb:
    def __init__(self) -> None:
        self.calls = []

    def add_hotkey(self, combo, callback, *args, **kwargs):
        handle = len(self.calls)
        self.calls.append((combo, callback, kwargs))
        return handle

    def remove_hotkey(self, handle):  # noqa: D401
        pass


def test_hotkey_manager_hold_mode_fires_start_and_stop():
    kb = _FakeKb()
    started, stopped = [], []
    mgr = HotkeyManager(
        "ctrl+alt+d",
        lambda: started.append(1),
        lambda: stopped.append(1),
        hold_to_talk=True,
        keyboard_mod=kb,
    )
    mgr.start()
    press = [c for c in kb.calls if not c[2].get("trigger_on_release")][0][1]
    release = [c for c in kb.calls if c[2].get("trigger_on_release")][0][1]
    press()
    release()
    assert started and stopped


def test_hotkey_manager_toggle_mode_alternates():
    kb = _FakeKb()
    started, stopped = [], []
    mgr = HotkeyManager(
        "ctrl+alt+d",
        lambda: started.append(1),
        lambda: stopped.append(1),
        hold_to_talk=False,
        keyboard_mod=kb,
    )
    mgr.start()
    cb = kb.calls[0][1]
    cb()
    cb()
    cb()
    assert len(started) == 2 and len(stopped) == 1


def test_hotkey_manager_uses_real_keyboard_by_default():
    mgr = HotkeyManager("ctrl+alt+d", lambda: None, lambda: None)
    assert mgr._kb is not None


# --------------------------------------------------------------- ipc commands


def test_dictation_commands_set_request():
    app = _app()

    async def run():
        await app._handle_message({"type": "start_dictation"})
        assert app._ptt_request == "start"
        await app._handle_message({"type": "stop_dictation"})
        assert app._ptt_request == "stop"

    asyncio.run(run())


def test_set_wake_command_toggles_and_broadcasts():
    app = _app()
    app._wake = object()
    app._state = "idle"

    async def run():
        await app._handle_message({"type": "set_wake", "value": True})
        assert app._wake_enabled is True
        states = [e for e in app._ipc.events if e.get("type") == "state"]
        assert any(e.get("wake_enabled") is True for e in states)
        await app._handle_message({"type": "set_wake", "value": False})
        assert app._wake_enabled is False

    asyncio.run(run())


def test_get_state_includes_wake_and_ptt():
    app = _app()
    app._wake_enabled = True
    app._ptt_active = False

    async def run():
        resp = await app._handle_message({"type": "get_state"})
        assert resp["wake_enabled"] is True
        assert resp["ptt_active"] is False

    asyncio.run(run())


# --------------------------------------------------------------- dictation stt


def test_dictation_uses_dedicated_engine():
    app = _app()
    voice = _FakeStt("voice")
    dict_ = _FakeStt("dictation")
    app._stt = voice
    app._dict_stt = dict_

    async def run():
        await app._process_utterance(np.zeros(16000, dtype=np.float32), source="dictation")

    asyncio.run(run())
    assert dict_.calls == 1
    assert voice.calls == 0
    sources = [e.get("source") for e in app._ipc.events if e.get("type") == "transcript"]
    assert "dictation" in sources


def test_voice_path_uses_main_engine():
    app = _app()
    voice = _FakeStt("voice")
    dict_ = _FakeStt("dictation")
    app._stt = voice
    app._dict_stt = dict_

    async def run():
        await app._process_utterance(np.zeros(16000, dtype=np.float32), source="voice")

    asyncio.run(run())
    assert voice.calls == 1
    assert dict_.calls == 0


def test_dictation_config_present_in_defaults():
    cfg = DaemonConfig()
    assert cfg.dictation.hotkey
    assert cfg.wake.enabled is True
