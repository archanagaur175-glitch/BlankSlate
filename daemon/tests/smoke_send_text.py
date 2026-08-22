"""Headless smoke test for the BlankSlate local AI path (P5 + P2).

Boots the real daemon agent stack with a fake IPC bridge, starts a local
Ollama (reusing the first-run fetch logic), pulls a small model, then sends a
canned prompt through ``DaemonApp.send_text`` and asserts a real LLM response
arrives within a timeout. This is the automated release gate: it proves the
engine actually answers, not just that the process starts.

Run directly (for local P7 verification):
    python -m tests.smoke_send_text

Or via pytest (CI):
    pytest tests/smoke_send_text.py
"""

from __future__ import annotations

import asyncio
import os
import subprocess
import sys
import time
from pathlib import Path

# Allow running both as a module (pytest) and as a script.
if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from blankslate.app import DaemonApp  # noqa: E402
from blankslate.config import DaemonConfig  # noqa: E402
from blankslate.ollama_fetch import ensure_ollama  # noqa: E402
from blankslate.resources import register_ollama_data_dir, resolve_ollama_binary  # noqa: E402


OLLAMA_HOST = "127.0.0.1:11434"
SMALL_MODEL = "qwen2.5:0.5b"
EMBED_MODEL = "nomic-embed-text"
PROMPT = "Reply with exactly the single word: PONG"
TIMEOUT_S = 240


class FakeIpc:
    def __init__(self) -> None:
        self.messages: list[dict] = []
        self.on_message = None

    async def start(self) -> None:
        pass

    async def stop(self) -> None:
        pass

    def write_info_file(self, _path) -> None:  # noqa: D401
        pass

    async def broadcast(self, message: dict) -> None:
        self.messages.append(message)


class StubTTS:
    def speak(self, text: str) -> None:
        pass


class StubJudge:
    def __init__(self, query: str) -> None:
        self._query = query

    async def judge(self, text: str, context: str = ""):  # noqa: ANN001
        from blankslate.nlu.intent import Intent

        return Intent(directed=True, query=text, source="stub")


async def _wait_for_ollama(base_url: str, timeout: float) -> bool:
    import requests

    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            r = requests.get(f"{base_url}/api/version", timeout=3)
            if r.status_code == 200:
                return True
        except Exception:  # noqa: BLE001
            pass
        await asyncio.sleep(1.0)
    return False


async def _ensure_ollama_running() -> tuple[str, subprocess.Popen | None, Path]:
    """Return (binary_path, proc_or_None, models_dir). Starts Ollama if needed."""
    data_dir = Path(os.environ.get("BLANKSLATE_SMOKE_DIR", "")) or (
        Path.home() / ".blankslate_smoke_tmp"
    )
    data_dir.mkdir(parents=True, exist_ok=True)
    models_dir = data_dir / "ollama_models"

    binary = resolve_ollama_binary()
    if binary is None:
        binary = await ensure_ollama(data_dir / "ollama_fetch")
    if binary is None:
        raise RuntimeError("Could not locate or fetch an Ollama binary")

    # If a server is already answering, reuse it (don't spawn a second one).
    if await _wait_for_ollama(f"http://{OLLAMA_HOST}", 3.0):
        return binary, None, models_dir

    env = dict(os.environ)
    env["OLLAMA_HOST"] = OLLAMA_HOST
    env["OLLAMA_MODELS"] = str(models_dir)
    proc = subprocess.Popen(
        [str(binary), "serve"],
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )
    if not await _wait_for_ollama(f"http://{OLLAMA_HOST}", 60.0):
        proc.terminate()
        raise RuntimeError("Ollama server did not become reachable")
    return binary, proc, models_dir


async def run_smoke() -> None:
    print("[smoke] locating/starting Ollama…", flush=True)
    binary, proc, models_dir = await _ensure_ollama_running()
    print(f"[smoke] Ollama up via {binary}", flush=True)
    base_url = f"http://{OLLAMA_HOST}"
    try:
        cfg = DaemonConfig()
        cfg.llm.base_url = base_url
        cfg.llm.model = SMALL_MODEL
        cfg.llm.timeout_s = 120.0
        cfg.tool_router.embedding_model = EMBED_MODEL
        cfg.wake.enabled = False
        cfg.demo_echo = False
        data_dir = (Path.home() / ".blankslate_smoke_tmp" / "data")
        cfg.data_dir = str(data_dir)
        cfg.ensure_dirs()
        register_ollama_data_dir(data_dir / "ollama")

        app = DaemonApp(cfg)
        app._ipc = FakeIpc()
        app._tts = StubTTS()
        app._build_agent_stack()
        # Set AFTER _build_agent_stack, which installs its own IntentJudge.
        app._judge = StubJudge("")
        app._agent_available = True
        app._loop = asyncio.get_running_loop()

        print(f"[smoke] ensuring models ({SMALL_MODEL}, {EMBED_MODEL})…", flush=True)
        await app._ensure_models()
        assert await app._ollama_healthy(), "Ollama not healthy before prompt"
        print("[smoke] models ready; sending canned prompt…", flush=True)

        start = time.time()
        await app.send_text(PROMPT)

        reply = None
        while time.time() - start < TIMEOUT_S:
            for msg in app._ipc.messages:
                if msg.get("type") == "agent.agent_reply":
                    text = str(msg.get("text", ""))
                    if text and not text.startswith("[error]"):
                        reply = text
                        break
            if reply is not None:
                break
            await asyncio.sleep(0.5)

        if reply is None:
            print("[smoke] TIMEOUT — dumping all IPC messages:", flush=True)
            for m in app._ipc.messages:
                print("  ", m, flush=True)
        assert reply is not None, "No real LLM response received within timeout"
        print(f"SMOKE OK: got response: {reply!r}", flush=True)
    finally:
        if proc is not None:
            try:
                proc.terminate()
                proc.wait(timeout=15)
            except Exception:  # noqa: BLE001
                proc.kill()


if __name__ == "__main__":
    asyncio.run(run_smoke())
else:
    import pytest

    @pytest.mark.asyncio
    async def test_send_text_real_llm_response() -> None:
        await run_smoke()
