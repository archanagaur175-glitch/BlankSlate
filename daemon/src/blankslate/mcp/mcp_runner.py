"""MCP (Model Context Protocol) client manager with a warm session pool.

Wraps the official mcp Python SDK (MIT, mcp>=2.0). Config entries map server
names to either ``stdio`` (command + args) or ``url`` (streamable HTTP/SSE)
server specs. Sessions are kept warm in an LRU pool so repeated calls do not
pay process-spawn latency.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class McpServerConfig:
    name: str
    command: str = ""
    args: list[str] = field(default_factory=list)
    env: dict[str, str] = field(default_factory=dict)
    url: str = ""
    client_kwargs: dict = field(default_factory=dict)

    @classmethod
    def from_dict(cls, data: dict) -> McpServerConfig:
        return cls(
            name=str(data.get("name") or ""),
            command=str(data.get("command") or ""),
            args=list(data.get("args") or []),
            env=dict(data.get("env") or {}),
            url=str(data.get("url") or ""),
            client_kwargs=dict(data.get("client_kwargs") or {}),
        )


def _extract_texts(result: Any) -> list[str]:
    if isinstance(result, tuple):
        result = result[0] if result else None
    elif isinstance(result, dict) and "content" in result:
        result = result["content"]
    if result is None:
        return []
    texts: list[str] = []
    if isinstance(result, (list, tuple)):
        for item in result:
            if isinstance(item, dict):
                if item.get("type") == "text":
                    texts.append(str(item.get("text", "")))
            elif isinstance(item, str):
                texts.append(item)
            else:
                text = getattr(item, "text", None)
                if text:
                    texts.append(str(text))
    elif isinstance(result, str):
        texts.append(result)
    return texts


class McpRunner:
    def __init__(self, servers: list[McpServerConfig], pool_size: int = 4) -> None:
        self.pool_size = max(1, pool_size)
        self.servers = {s.name: s for s in servers}
        self._sessions: dict[str, list] = {}
        self._lock = asyncio.Lock()
        self._closed = False

    @classmethod
    def from_config_dicts(cls, raw: list[dict], pool_size: int = 4) -> McpRunner:
        servers = [McpServerConfig.from_dict(d) for d in (raw or [])]
        return cls(servers, pool_size)

    def list_servers(self) -> list[str]:
        return sorted(self.servers)

    def has_server(self, name: str) -> bool:
        return name in self.servers

    async def _connect(self, spec: McpServerConfig):
        from mcp import Client, StdioServerParameters

        if spec.url:
            session = Client(spec.url, **spec.client_kwargs)
        else:
            params = StdioServerParameters(command=spec.command, args=spec.args, env=spec.env or None)
            session = Client(params, **spec.client_kwargs)
        if hasattr(session, "initialize"):
            await session.initialize()
        return session

    async def _acquire(self, name: str):
        if name not in self.servers:
            raise KeyError(f"unknown MCP server: {name}")
        async with self._lock:
            pool = self._sessions.setdefault(name, [])
            if pool:
                return pool.pop(0)
        return await self._connect(self.servers[name])

    def _release(self, name: str, session) -> None:
        if self._closed:
            return
        pool = self._sessions.setdefault(name, [])
        if len(pool) < self.pool_size:
            pool.append(session)
        else:
            asyncio.ensure_future(self._dispose(session))

    async def _dispose(self, session) -> None:
        for close in ("close", "aclose"):
            fn = getattr(session, close, None)
            if callable(fn):
                try:
                    result = fn()
                    if asyncio.iscoroutine(result):
                        await result
                    return
                except Exception as exc:  # noqa: BLE001
                    logger.debug("mcp session close %s failed: %s", close, exc)

    async def call(self, server: str, tool_name: str, arguments: dict) -> list[str]:
        session = await self._acquire(server)
        try:
            result = await session.call_tool(
                {"serverName": server, "name": tool_name, "arguments": arguments}
            )
            return _extract_texts(result)
        finally:
            self._release(server, session)

    async def list_tools(self, server: str) -> list[dict]:
        session = await self._acquire(server)
        try:
            result = await session.list_tools({"serverName": server})
            tools = getattr(result, "tools", result)
            cleaned = []
            for tool in tools or []:
                if isinstance(tool, dict):
                    cleaned.append(tool)
                else:
                    cleaned.append(
                        {
                            "name": getattr(tool, "name", ""),
                            "description": getattr(tool, "description", ""),
                            "inputSchema": getattr(tool, "input_schema", getattr(tool, "inputSchema", {})),
                        }
                    )
            return cleaned
        finally:
            self._release(server, session)

    async def aclose(self) -> None:
        self._closed = True
        for name, pool in list(self._sessions.items()):
            for session in pool:
                await self._dispose(session)
            self._sessions[name] = []