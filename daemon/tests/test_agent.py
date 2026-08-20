"""Tests for the agent loop: planning, tool calls, events."""

import asyncio

from blankslate.agent import Agent, AgentOptions
from blankslate.llm.base import LLMResult, LLMToolCall
from blankslate.nlu.planner import TaskPlanner
from blankslate.router.tool_router import ToolRouter
from blankslate.tools.native import NativeToolRunner


class _ScriptedLlm:
    """Emits a scripted sequence of chat responses."""

    def __init__(self, script) -> None:
        self.script = list(script)
        self.calls = []

    async def chat(self, messages, tools=None, temperature=0.3, max_tokens=None):
        self.calls.append({"messages": messages, "tools": tools})
        return self.script.pop(0)


def _build_agent(tmp_path, llm, planner=None, collect_events=None):
    router = ToolRouter(strategy="keyword", top_k=10)
    native = NativeToolRunner(tmp_path)
    planner = planner or TaskPlanner(llm=None)
    return Agent(
        llm=llm,
        router=router,
        native=native,
        planner=planner,
        options=AgentOptions(max_iterations=4),
        event_cb=collect_events or (lambda event, payload: None),
    )


def test_agent_answers_directly(tmp_path):
    llm = _ScriptedLlm([LLMResult(content="It is noon.")])
    agent = _build_agent(tmp_path, llm)
    reply = asyncio.run(agent.handle("what time is it", []))
    assert reply == "It is noon."


def test_agent_runs_tool_then_answers(tmp_path):
    llm = _ScriptedLlm(
        [
            LLMResult(tool_calls=[LLMToolCall(id="c1", name="get_current_time", arguments={})]),
            LLMResult(content="The current time is right now."),
        ]
    )
    agent = _build_agent(tmp_path, llm)
    reply = asyncio.run(agent.handle("what is the time", []))
    assert "right now" in reply
    audited_tool = llm.calls[1]["messages"][-1]
    assert audited_tool["role"] == "tool"
    assert audited_tool["content"]


def test_agent_emits_events(tmp_path):
    events = []
    llm = _ScriptedLlm(
        [
            LLMResult(tool_calls=[LLMToolCall(id="c1", name="get_current_time", arguments={})]),
            LLMResult(content="done."),
        ]
    )
    agent = _build_agent(tmp_path, llm, collect_events=lambda e, p: events.append((e, p)))
    asyncio.run(agent.handle("time please", []))
    kinds = [e for e, _ in events]
    assert "agent_start" in kinds
    assert "tool_call" in kinds
    assert "agent_reply" in kinds


def test_agent_multi_step_plan(tmp_path):
    llm = _ScriptedLlm([LLMResult(content="step one done"), LLMResult(content="step two done")])

    class _TwoStepPlanner:
        async def plan(self, query):
            return ["step one", "step two"]

    agent = _build_agent(tmp_path, llm, planner=_TwoStepPlanner())
    reply = asyncio.run(agent.handle("do two things", []))
    assert "step one done" in reply
    assert "step two done" in reply


def test_agent_empty_query(tmp_path):
    llm = _ScriptedLlm([])
    agent = _build_agent(tmp_path, llm)
    assert asyncio.run(agent.handle("   ", [])) == ""


def test_agent_stops_after_max_iterations(tmp_path):
    class _CircularLlm:
        async def chat(self, messages, tools=None, temperature=0.3, max_tokens=None):
            return LLMResult(tool_calls=[LLMToolCall(id="x", name="get_current_time", arguments={})])

    agent = Agent(
        llm=_CircularLlm(),
        router=ToolRouter(strategy="keyword", top_k=10),
        native=NativeToolRunner(tmp_path),
        planner=TaskPlanner(llm=None),
        options=AgentOptions(max_iterations=2),
    )
    reply = asyncio.run(agent.handle("loop", []))
    assert reply  # returns last tool output


def test_agent_mcp_tools(tmp_path):
    llm = _ScriptedLlm(
        [
            LLMResult(tool_calls=[LLMToolCall(id="c", name="files__read_file", arguments={"p": "x"})]),
            LLMResult(content="read the file"),
        ]
    )
    events = []

    async def lister(server):
        return [{"name": "read_file", "description": "read a file", "inputSchema": {"type": "object"}}]

    async def caller(server, tool, arguments):
        assert tool == "read_file"
        return "file contents"

    agent = Agent(
        llm=llm,
        router=ToolRouter(strategy="keyword", top_k=10),
        native=NativeToolRunner(tmp_path),
        planner=TaskPlanner(llm=None),
        options=AgentOptions(max_iterations=4),
        event_cb=lambda e, p: events.append((e, p)),
        mcp_lister=lister,
        mcp_caller=caller,
        mcp_server_names=["files"],
    )
    reply = asyncio.run(agent.handle("read my file", []))
    assert reply == "read the file"
    assert ("tool_call", {"name": "files__read_file", "arguments": {"p": "x"}}) in events


def test_unknown_native_tool_reports_error(tmp_path):
    llm = _ScriptedLlm(
        [
            LLMResult(tool_calls=[LLMToolCall(id="c", name="explode_everything", arguments={})]),
            LLMResult(content="ok"),
        ]
    )
    agent = _build_agent(tmp_path, llm)
    reply = asyncio.run(agent.handle("do it", []))
    assert reply == "ok"