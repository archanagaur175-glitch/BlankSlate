"""The agentic loop that turns a user query into tool calls + a final answer."""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass

from blankslate.llm.base import LLMProvider
from blankslate.nlu.planner import TaskPlanner
from blankslate.router.tool_router import ToolRouter, ToolSpec
from blankslate.tools.native import NativeToolRunner

logger = logging.getLogger(__name__)

EventCb = Callable[[str, dict], Awaitable[None] | None]


@dataclass
class AgentOptions:
    system_prompt: str = (
        "You are BlankSlate, a private, local-first voice assistant. Be concise "
        "and accurate. Use tools when they help, and clearly report what you did."
    )
    max_iterations: int = 6
    temperature: float = 0.3


class Agent:
    """Runs the plan-then-execute tool loop over a possibly multi-step query."""

    def __init__(
        self,
        llm: LLMProvider,
        router: ToolRouter,
        native: NativeToolRunner,
        planner: TaskPlanner,
        options: AgentOptions | None = None,
        event_cb: EventCb | None = None,
        mcp_lister=None,
        mcp_caller=None,
        mcp_server_names: list[str] | None = None,
    ) -> None:
        self.llm = llm
        self.router = router
        self.native = native
        self.planner = planner
        self.options = options or AgentOptions()
        self.event_cb = event_cb or (lambda event, payload: None)
        self.mcp_lister = mcp_lister  # async (server) -> list[dict]
        self.mcp_caller = mcp_caller  # async (server, tool, args) -> str
        self.mcp_server_names = mcp_server_names or []

    async def _emit(self, event: str, payload: dict) -> None:
        try:
            await self.event_cb(event, payload)
        except Exception as exc:  # noqa: BLE001
            logger.debug("event callback failed: %s", exc)

    async def _collect_specs(self) -> list[ToolSpec]:
        specs = self.native.specs()
        if self.mcp_lister is not None:
            try:
                for server in self.mcp_server_names:
                    for tool in await self.mcp_lister(server):
                        name = str(tool.get("name") or "")
                        if not name:
                            continue
                        specs.append(
                            ToolSpec(
                                name=f"{server}__{name}",
                                description=str(tool.get("description") or ""),
                                parameters=tool.get("inputSchema")
                                or tool.get("input_schema")
                                or {"type": "object", "properties": {}},
                            )
                        )
            except Exception as exc:  # noqa: BLE001
                logger.warning("mcp tool listing failed: %s", exc)
        return specs

    async def _run_tool(self, name: str, arguments: dict) -> str:
        if "__" in name:
            server, _, tool = name.partition("__")
            if self.mcp_caller is not None:
                return await self.mcp_caller(server, tool, arguments)
        return await self.native.run(name, arguments)

    async def handle(self, query: str, history: list[dict]) -> str:
        query = (query or "").strip()
        if not query:
            return ""
        await self._emit("agent_start", {"query": query})
        steps = await self.planner.plan(query)
        if len(steps) <= 1:
            return await self._execute(query, history)

        outputs = []
        for idx, step in enumerate(steps, start=1):
            await self._emit("plan_step", {"index": idx, "step": step})
        for idx, step in enumerate(steps):
            step_history = list(history)
            if outputs:
                step_history.append({"role": "assistant", "content": outputs[-1]})
            text = await self._execute(step, step_history)
            outputs.append(text or "")
            await self._emit("step_result", {"index": idx, "result": text})
        merged = "\n".join(o for o in outputs if o)
        return merged or "\n".join(steps)

    async def _execute(self, query: str, history: list[dict]) -> str:
        messages: list[dict] = [{"role": "system", "content": self.options.system_prompt}]
        messages.extend(history[-8:])
        messages.append({"role": "user", "content": query})

        specs = await self._collect_specs()
        last_content = ""
        for _ in range(self.options.max_iterations):
            selected = await self.router.select(query, specs)
            schemas = [s.to_schema() for s in selected]
            result = await self.llm.chat(
                messages,
                tools=schemas or None,
                temperature=self.options.temperature,
            )

            if not result.tool_calls:
                reply = (result.content or "").strip()
                last_content = reply
                await self._emit("agent_reply", {"text": reply})
                return reply

            assistant_msg: dict = {"role": "assistant", "content": result.content or ""}
            if result.tool_calls:
                calls = [
                    {"id": c.id, "type": "function", "function": {"name": c.name, "arguments": c.arguments}}
                    for c in result.tool_calls
                ]
                assistant_msg["tool_calls"] = calls
            messages.append(assistant_msg)

            for call in result.tool_calls:
                await self._emit("tool_call", {"name": call.name, "arguments": call.arguments})
                output = await self._run_tool(call.name, call.arguments)
                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": call.id or call.name,
                        "content": output[:4000],
                    }
                )
                last_content = output

        await self._emit("agent_reply", {"text": last_content})
        return last_content or "I ran out of iterations trying to complete that."