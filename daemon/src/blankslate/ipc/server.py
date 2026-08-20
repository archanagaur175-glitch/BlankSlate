"""Local-only IPC: a loopback WebSocket server with per-run token auth.

The server binds to 127.0.0.1 on an OS-assigned port and writes an endpoint
file (``ipc.json``) that the HUD client reads. Events are broadcast to every
connected client; clients may also send commands handled by the app.
"""

from __future__ import annotations

import asyncio
import json
import logging
import secrets
from collections.abc import Awaitable, Callable
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from websockets.asyncio.server import ServerConnection, serve
from websockets.exceptions import ConnectionClosed

from blankslate import __version__

logger = logging.getLogger(__name__)

MessageHandler = Callable[[dict], Awaitable[dict | None]]


def restrict_file_acl(path: Path) -> None:
    """Best-effort ACL: only the current user and SYSTEM may touch ``path``."""
    try:
        import win32api
        import win32security

        dacl = win32security.ACL()

        def add_user(name: str) -> None:
            try:
                sid, _, _ = win32security.LookupAccountName(None, name)
            except Exception:  # noqa: BLE001
                return
            dacl.AddAccessAllowedAceEx(win32security.ACL_REVISION, 0, FILE_ALL_ACCESS, sid)

        add_user(win32api.GetUserName())
        add_user("SYSTEM")
        add_user("NT AUTHORITY\\SYSTEM")

        security = win32security.GetFileSecurity(str(path), win32security.DACL_SECURITY_INFORMATION)
        security.SetSecurityDescriptorDacl(1, dacl, 0)
        win32security.SetFileSecurity(str(path), win32security.DACL_SECURITY_INFORMATION, security)
    except Exception as exc:  # noqa: BLE001
        logger.debug("could not restrict ACL on %s: %s", path, exc)


FILE_ALL_ACCESS = 0x001F01FF


class IpcServer:
    def __init__(self, host: str = "127.0.0.1", port: int = 0, token: str | None = None) -> None:
        self.host = host
        self.port = port
        self.token = token or secrets.token_urlsafe(24)
        self.on_message: MessageHandler | None = None
        self._server: asyncio.Server | None = None
        self._url: str | None = None
        self._broadcast_q: asyncio.Queue[dict] = asyncio.Queue()
        self._clients: set[ServerConnection] = set()
        self._writer_tasks: set[asyncio.Task] = set()

    @property
    def url(self) -> str:
        if self._url is None:
            raise RuntimeError("IpcServer not started")
        return self._url

    async def start(self) -> str:
        self._server = await serve(self._handler, self.host, self.port, max_size=1 << 20)
        sock = self._server.sockets[0].getsockname()
        self.port = int(sock[1])
        self._url = f"ws://{self.host}:{self.port}/?token={self.token}"
        logger.info("IPC listening on %s", self._url.split("?")[0])
        return self._url

    def write_info_file(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "url": self.url,
            "host": self.host,
            "port": self.port,
            "token": self.token,
            "version": __version__,
        }
        path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        restrict_file_acl(path)

    async def stop(self) -> None:
        for ws in list(self._clients):
            try:
                await ws.close(1001, "daemon shutting down")
            except Exception:  # noqa: BLE001
                pass
        for task in self._writer_tasks:
            task.cancel()
        if self._server is not None:
            self._server.close()
            await self._server.wait_closed()

    async def broadcast(self, event: dict) -> None:
        await self._broadcast_q.put(event)

    def _token_ok(self, ws: ServerConnection) -> bool:
        try:
            token = parse_qs(urlparse(ws.request.path).query).get("token", [None])[0]
        except Exception:  # noqa: BLE001
            token = None
        return secrets.compare_digest(token or "", self.token)

    async def _handler(self, ws: ServerConnection) -> None:
        if not self._token_ok(ws):
            await ws.close(4001, "invalid token")
            return
        self._clients.add(ws)
        writer = asyncio.create_task(self._writer(ws))
        self._writer_tasks.add(writer)
        try:
            await ws.send(json.dumps({"type": "welcome", "version": __version__}))
            async for raw in ws:
                try:
                    message = json.loads(raw)
                except json.JSONDecodeError:
                    continue
                if self.on_message is None:
                    continue
                response = await self.on_message(message)
                if response is not None:
                    await ws.send(json.dumps(response))
        except ConnectionClosed:
            pass
        finally:
            self._clients.discard(ws)
            writer.cancel()
            self._writer_tasks.discard(writer)

    async def _writer(self, ws: ServerConnection) -> None:
        try:
            while True:
                event = await self._broadcast_q.get()
                await ws.send(json.dumps(event, default=str))
        except ConnectionClosed:
            pass
