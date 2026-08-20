"""Tests for the MCP runner session pool using fake sessions."""

import asyncio

import pytest

from blankslate.mcp.mcp_runner import McpRunner, McpServerConfig, _extract_texts


class _FakeSession:
    def __init__(self, name: str) -> None:
        self.name = name
        self.closed = False
        self.client_kwargs = {}

    async def initialize(self) -> None:
        pass

    async def call_tool(self, request: dict) -> list:
        return [{"type": "text", "text": f"{self.name}:{request['name']}:{request.get('arguments')}"}]

    async def list_tools(self, request: dict) -> object:
        class R:
            tools = [{"name": "fake_read", "description": "reads", "inputSchema": {"type": "object"}}]

        return R()

    async def close(self) -> None:
        self.closed = True


def test_config_from_dict():
    cfg = McpServerConfig.from_dict(
        {"name": "files", "command": "npx", "args": ["-y", "server"], "env": {"A": "1"}}
    )
    assert cfg.name == "files"
    assert cfg.command == "npx"
    assert cfg.args == ["-y", "server"]
    assert cfg.env == {"A": "1"}


def test_runner_list_servers():
    runner = McpRunner([McpServerConfig(name="b"), McpServerConfig(name="a")])
    assert runner.list_servers() == ["a", "b"]
    assert runner.has_server("a")


def test_runner_unknown_server():
    runner = McpRunner([])
    with pytest.raises(KeyError):
        asyncio.run(runner.call("nope", "t", {}))


def test_extract_texts():
    assert _extract_texts([{"type": "text", "text": "hi"}]) == ["hi"]
    assert _extract_texts("plain") == ["plain"]
    assert _extract_texts([{"type": "image"}]) == []
    assert _extract_texts(None) == []


async def _test_pool_reuse():
    made: list[_FakeSession] = []

    async def factory(_spec=None):
        session = _FakeSession("s")
        made.append(session)
        return session

    runner = McpRunner([McpServerConfig(name="srv")])
    runner._connect = factory

    first = await runner.call("srv", "t", {"k": "v"})
    assert first == ["s:t:{'k': 'v'}"]

    second = await runner.call("srv", "t2", {})
    assert len(made) == 1, "second call should reuse the pooled session"
    assert second == ["s:t2:{}"]
    await runner.aclose()


def test_pool_reuse():
    asyncio.run(_test_pool_reuse())


async def _test_list_tools_conversion():
    runner = McpRunner([McpServerConfig(name="srv")])

    async def factory(_spec=None):
        return _FakeSession("srv")

    runner._connect = factory
    tools = await runner.list_tools("srv")
    assert tools == [{"name": "fake_read", "description": "reads", "inputSchema": {"type": "object"}}]
    await runner.aclose()


def test_list_tools_conversion():
    asyncio.run(_test_list_tools_conversion())


def test_extract_texts_from_obj():
    class _Content:
        def __init__(self):
            self.type = "text"
            self.text = "obj-text"

    assert _extract_texts([_Content()]) == ["obj-text"]


def test_call_tuple_result():
    assert _extract_texts(([{"type": "text", "text": "a"}], None)) == ["a"]