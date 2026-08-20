"""Tests for the intent judge and task planner."""

import asyncio

from blankslate.nlu.intent import IntentJudge, _strip_wake_word, heuristic_judge
from blankslate.nlu.planner import TaskPlanner


def test_wake_word_stripped():
    judge = IntentJudge(llm=None, wake_words=["hey jarvis"])
    intent = asyncio.run(judge.judge("hey jarvis what time is it"))
    assert intent.directed is True
    assert intent.query == "what time is it"


def test_wake_word_at_end():
    judge = IntentJudge(llm=None, wake_words=["hey jarvis"])
    intent = asyncio.run(judge.judge("what is the weather hey jarvis"))
    assert intent.directed is True
    assert "hey jarvis" not in intent.query


def test_no_wake_word_undirected():
    judge = IntentJudge(llm=None, wake_words=["hey jarvis"])
    intent = asyncio.run(judge.judge("totally unrelated chatter"))
    assert intent.directed is False
    assert intent.query == ""


def test_empty_text_undirected():
    judge = IntentJudge(llm=None, wake_words=["hey jarvis"])
    intent = asyncio.run(judge.judge(""))
    assert intent.directed is False


def test_multiple_wake_words():
    judge = IntentJudge(llm=None, wake_words=["hey jarvis", "Hey Jarvis"])
    intent = asyncio.run(judge.judge("Hey Jarvis set a timer"))
    assert intent.directed is True


class _FakeLlm:
    def __init__(self, payload: str) -> None:
        self.payload = payload

    async def chat(self, messages, tools=None, temperature=0.3, max_tokens=None):
        from blankslate.llm.base import LLMResult

        return LLMResult(content=self.payload)


def test_llm_judge_directed():
    judge = IntentJudge(llm=_FakeLlm('{"directed": true, "query": "open the browser"}'), wake_words=["hey jarvis"])
    intent = asyncio.run(judge.judge("hey jarvis open the browser"))
    assert intent.directed is True
    assert intent.query == "open the browser"
    assert intent.source == "llm"


def test_llm_judge_undirected():
    judge = IntentJudge(llm=_FakeLlm('{"directed": false, "query": ""}'), wake_words=["hey jarvis"])
    intent = asyncio.run(judge.judge("mom, can you pass the salt"))
    assert intent.directed is False


def test_llm_judge_fails_falls_back_heuristic():
    class _Boom:
        async def chat(self, messages, tools=None, temperature=0.3, max_tokens=None):
            raise RuntimeError("offline")

    judge = IntentJudge(llm=_Boom(), wake_words=["hey jarvis"])
    intent = asyncio.run(judge.judge("hey jarvis how are you"))
    assert intent.directed is True
    assert intent.source == "heuristic"


def test_heuristic_judge_direct():
    intent = heuristic_judge("hey jarvis play music", ["hey jarvis"])
    assert intent.directed is True


def test_strip_wake_word():
    assert _strip_wake_word("hey jarvis: do it", ["hey jarvis"]) == "do it"


def test_planner_single_step_when_simple():
    planner = TaskPlanner(llm=None)
    plan = asyncio.run(planner.plan("what time is it"))
    assert plan == ["what time is it"]


def test_planner_heuristic_split():
    planner = TaskPlanner(llm=None)
    plan = asyncio.run(planner.plan("open spotify and then play jazz"))
    assert len(plan) == 2
    assert plan[0] == "open spotify"
    assert plan[1] == "play jazz"


def test_planner_llm_plan():
    planner = TaskPlanner(llm=_FakeLlm('{"plan": ["open browser", "search docs"], "needs_tools": true}'))
    plan = asyncio.run(planner.plan("open browser and search docs"))
    assert plan == ["open browser", "search docs"]


def test_planner_empty():
    planner = TaskPlanner(llm=None)
    assert asyncio.run(planner.plan("")) == []