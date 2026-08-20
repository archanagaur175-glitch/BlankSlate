import json

import pytest
from websockets.asyncio.client import connect
from websockets.exceptions import ConnectionClosed

from blankslate.ipc.server import IpcServer


async def test_welcome_broadcast_and_commands() -> None:
    server = IpcServer(host="127.0.0.1", port=0)

    async def handler(message: dict) -> dict | None:
        if message.get("type") == "ping":
            return {"type": "pong", "ok": True}
        return {"type": "error", "ok": False, "error": "unknown"}

    server.on_message = handler
    url = await server.start()
    async with connect(url) as ws:
        welcome = json.loads(await ws.recv())
        assert welcome["type"] == "welcome"

        await server.broadcast({"type": "transcript", "text": "hello"})
        event = json.loads(await ws.recv())
        assert event == {"type": "transcript", "text": "hello"}

        await ws.send(json.dumps({"type": "ping"}))
        response = json.loads(await ws.recv())
        assert response["ok"] is True

    await server.stop()


async def test_bad_token_rejected(tmp_path) -> None:
    server = IpcServer(host="127.0.0.1", port=0)
    url = await server.start()
    server.write_info_file(tmp_path / "ipc.json")
    info = json.loads((tmp_path / "ipc.json").read_text(encoding="utf-8"))
    assert info["url"] == url
    assert info["port"] == server.port

    bad = url.replace(f"token={server.token}", "token=wrong")
    with pytest.raises(ConnectionClosed):
        async with connect(bad) as ws:
            await ws.recv()

    await server.stop()


async def test_info_file_contains_credentials(tmp_path) -> None:
    server = IpcServer(host="127.0.0.1", port=0)
    await server.start()
    path = tmp_path / "ipc.json"
    server.write_info_file(path)
    data = json.loads(path.read_text(encoding="utf-8"))
    assert data["token"] == server.token
    assert data["host"] == "127.0.0.1"
    assert data["port"] == server.port
    assert data["url"] == server.url
    await server.stop()
