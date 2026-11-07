"""Loopback WebSocket IPC between the daemon and the BlankSlate HUD.

The daemon runs a WS server on 127.0.0.1 (ephemeral port), writes
``%LOCALAPPDATA%/BlankSlate/ipc.json`` with the connection URL, and:
  * broadcasts daemon events as JSON Text frames (the HUD forwards these as
    ``daemon_event`` Tauri events), and
  * accepts command JSON frames from the HUD (``send_message`` /
    ``send_text_message``) and dispatches them to registered handlers.

This replaces the upstream ``desktop_app.face_widget`` callback contract so the
Tauri HUD can drive and observe the daemon without the PyQt desktop app.
"""

from __future__ import annotations

import asyncio
import json
import os
import threading
from pathlib import Path
from typing import Any, Callable, Optional

try:
    import websockets
except Exception:  # websockets is only needed when IPC is actually started
    websockets = None

from .debug import debug_log

DEFAULT_HOST = "127.0.0.1"
_APP_NAME = "BlankSlate"

# State name constants consumed by the HUD (mirror upstream JarvisState usage).
STATE_LISTENING = "listening"
STATE_IDLE = "idle"
STATE_THINKING = "thinking"
STATE_DICTATING = "dictating"
STATE_SPEAKING = "speaking"


def _ipc_info_path() -> Path:
    base = os.environ.get("LOCALAPPDATA") or os.path.expanduser("~/.local/share")
    return Path(base) / _APP_NAME / "ipc.json"


class IpcHub:
    def __init__(self) -> None:
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._server = None
        self._clients: set = set()
        self._queue: Optional[asyncio.Queue] = None
        self._cmd_handlers: dict[str, Callable[[dict], None]] = {}
        self._thread: Optional[threading.Thread] = None
        self._ready = threading.Event()
        self.host = DEFAULT_HOST
        self.port = 0
        self.version = "0.1.0"
        # Cached latest state/ollama_fetch so a HUD that connects after the
        # daemon has already emitted them still receives the current status.
        self._last_state: Optional[dict] = None
        self._last_ollama_fetch: Optional[dict] = None

    # -- lifecycle ---------------------------------------------------------
    def start(self, host: str = DEFAULT_HOST, version: str = "0.1.0") -> None:
        if websockets is None:
            debug_log("ipc: 'websockets' not installed; IPC disabled", "ipc")
            return
        # Clear any stale descriptor left behind by a previous (crashed) run.
        try:
            os.remove(_ipc_info_path())
        except Exception:
            pass
        self.host = host
        self.version = version
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()
        self._ready.wait(timeout=10)

    def _run(self) -> None:
        try:
            asyncio.run(self._async_main())
        except Exception as e:  # pragma: no cover - server failure is non-fatal
            debug_log(f"ipc server crashed: {e}", "ipc")

    async def _async_main(self) -> None:
        self._loop = asyncio.get_event_loop()
        self._queue = asyncio.Queue()

        async def handler(ws, path=None):
            self._clients.add(ws)
            try:
                await ws.send(json.dumps({"type": "welcome", "version": self.version}))
                # Replay the latest cached status so late-connecting HUDs
                # (or reconnects) immediately reflect current state/fetch.
                if self._last_state is not None:
                    await ws.send(json.dumps(self._last_state))
                if self._last_ollama_fetch is not None:
                    await ws.send(json.dumps(self._last_ollama_fetch))
                async for message in ws:
                    try:
                        cmd = json.loads(message)
                    except Exception:
                        continue
                    if isinstance(cmd, dict):
                        self._dispatch(cmd)
            except Exception as e:
                debug_log(f"ipc client handler error: {e}", "ipc")
            finally:
                self._clients.discard(ws)

        async def consumer():
            while True:
                item = await self._queue.get()
                if item is None:
                    break
                await self._drain(item)

        self._consumer = asyncio.ensure_future(consumer())
        self._server = await websockets.serve(handler, self.host, 0)
        self.port = self._server.sockets[0].getsockname()[1]
        self._write_ipc_json()
        self._ready.set()
        try:
            await asyncio.Future()  # run until cancelled
        finally:
            try:
                self._server.close()
                await self._server.wait_closed()
            except Exception:
                pass
            self._consumer.cancel()
            try:
                os.remove(_ipc_info_path())
            except Exception:
                pass

    async def _drain(self, item: dict) -> None:
        text = json.dumps(item, ensure_ascii=False)
        for ws in list(self._clients):
            try:
                await ws.send(text)
            except Exception:
                pass

    def _dispatch(self, cmd: dict) -> None:
        ctype = cmd.get("type")
        cb = self._cmd_handlers.get(ctype)
        if cb is None:
            debug_log(f"ipc: no handler for command {ctype!r}", "ipc")
            return
        try:
            cb(cmd)
        except Exception as e:
            debug_log(f"ipc command handler error ({ctype}): {e}", "ipc")

    def register_handler(self, cmd_type: str, cb: Callable[[dict], None]) -> None:
        self._cmd_handlers[cmd_type] = cb

    # -- outbound ----------------------------------------------------------
    def broadcast(self, event: dict) -> None:
        if self._loop is None or self._queue is None:
            return
        try:
            self._loop.call_soon_threadsafe(self._queue.put_nowait, event)
        except Exception:
            pass

    def broadcast_state(
        self,
        status: str,
        *,
        listening: Optional[bool] = None,
        wake_enabled: Optional[bool] = None,
        ptt_active: Optional[bool] = None,
    ) -> None:
        ev: dict[str, Any] = {"type": "state", "status": status}
        if listening is not None:
            ev["listening"] = listening
        if wake_enabled is not None:
            ev["wake_enabled"] = wake_enabled
        if ptt_active is not None:
            ev["ptt_active"] = ptt_active
        self._last_state = ev
        self.broadcast(ev)

    def broadcast_ollama_fetch(self, stage: str, percent: int, eta: int = 0) -> None:
        ev: dict[str, Any] = {
            "type": "ollama_fetch",
            "stage": stage,
            "percent": int(percent),
            "eta": int(eta),
        }
        self._last_ollama_fetch = ev
        self.broadcast(ev)

    def _write_ipc_json(self) -> None:
        try:
            path = _ipc_info_path()
            path.parent.mkdir(parents=True, exist_ok=True)
            info = {
                "url": f"ws://{self.host}:{self.port}",
                "host": self.host,
                "port": self.port,
                "version": self.version,
            }
            path.write_text(json.dumps(info), encoding="utf-8")
            debug_log(f"ipc: wrote {path} ({info['url']})", "ipc")
        except Exception as e:
            debug_log(f"ipc: failed to write ipc.json: {e}", "ipc")

    def stop(self) -> None:
        if self._loop is not None and self._queue is not None:
            try:
                self._loop.call_soon_threadsafe(self._queue.put_nowait, None)
            except Exception:
                pass
        if self._server is not None and self._loop is not None:
            try:
                self._loop.call_soon_threadsafe(self._server.close)
            except Exception:
                pass
        if self._thread is not None:
            self._thread.join(timeout=3)
        # Best-effort synchronous removal in case the async server thread was
        # forcibly terminated at interpreter exit and never ran its finally.
        try:
            os.remove(_ipc_info_path())
        except Exception:
            pass


# Module-level singleton + convenience wrappers -------------------------------
_hub = IpcHub()


def start_ipc(host: str = DEFAULT_HOST, version: str = "0.1.0") -> None:
    _hub.start(host=host, version=version)


def stop_ipc() -> None:
    _hub.stop()


def register_handler(cmd_type: str, cb: Callable[[dict], None]) -> None:
    _hub.register_handler(cmd_type, cb)


def broadcast(event: dict) -> None:
    _hub.broadcast(event)


def broadcast_state(status: str, **kw) -> None:
    _hub.broadcast_state(status, **kw)


def broadcast_ollama_fetch(stage: str, percent: int, eta: int = 0) -> None:
    _hub.broadcast_ollama_fetch(stage, percent, eta)
