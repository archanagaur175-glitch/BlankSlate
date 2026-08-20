"""Native tools v1: small safe capabilities available to the agent loop.

Kept tiny on purpose. Heavy, potentially destructive, or persistent actions
land in later milestones; everything here is read-only or easily reversible.
"""

from __future__ import annotations

import datetime
import json
import logging
import subprocess
import webbrowser
from pathlib import Path

import psutil

from blankslate.router.tool_router import ToolSpec

logger = logging.getLogger(__name__)


def _now() -> str:
    return datetime.datetime.now().astimezone().isoformat(timespec="seconds")


async def get_current_time(arguments: dict) -> str:
    return datetime.datetime.now().astimezone().strftime("%A, %B %d %Y %I:%M %p")


async def get_cpu_usage(arguments: dict) -> str:
    return f"CPU {psutil.cpu_percent(interval=0.2):.0f}%"


async def get_memory_usage(arguments: dict) -> str:
    mem = psutil.virtual_memory()
    return f"RAM {mem.percent:.0f}% used ({mem.used // (1024**3)} of {mem.total // (1024**3)} GiB)"


async def get_battery(arguments: dict) -> str:
    battery = psutil.sensors_battery()
    if battery is None:
        return "No battery detected."
    plugged = "plugged in" if battery.power_plugged else "on battery"
    return f"Battery at {battery.percent:.0f}%, {plugged}."


async def open_url(arguments: dict) -> str:
    url = str(arguments.get("url") or "").strip()
    if not url.startswith(("http://", "https://")):
        return "Result: url must start with http:// or https://"
    webbrowser.open(url)
    return f"Opened {url} in the default browser."


async def search_web(arguments: dict) -> str:
    query = str(arguments.get("query") or "").strip()
    if not query:
        return "Result: missing query"
    try:
        from ddgs import DDGS

        async with DDGS() as ddgs:
            results = await ddgs.atext(query, max_results=int(arguments.get("max_results") or 5))
        if not results:
            return "No results found."
        lines = []
        for i, item in enumerate(results[:5], start=1):
            title = item.get("title") or ""
            href = item.get("href") or item.get("url") or ""
            lines.append(f"{i}. {title}\n   {href}")
        return "Search results:\n" + "\n".join(lines)
    except Exception as exc:  # noqa: BLE001
        logger.warning("web search failed: %s", exc)
        return f"Search failed: {exc}"


async def launch_app(arguments: dict) -> str:
    target = str(arguments.get("app") or arguments.get("path") or "").strip()
    if not target:
        return "Result: missing app name or path"
    try:
        subprocess.Popen(
            target,
            shell=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        return f"Launched {target}."
    except Exception as exc:  # noqa: BLE001
        return f"Failed to launch {target}: {exc}"


async def set_reminder(arguments: dict, data_dir: Path) -> str:
    title = str(arguments.get("title") or "").strip()
    if not title:
        return "Result: missing title"
    when = str(arguments.get("when") or _now())
    reminders_path = Path(data_dir) / "reminders.json"
    reminders: list[dict] = []
    if reminders_path.exists():
        reminders = json.loads(reminders_path.read_text(encoding="utf-8"))
    reminders.append({"title": title, "when": when, "created": _now()})
    reminders_path.write_text(json.dumps(reminders, indent=2), encoding="utf-8")
    return f"Reminder set: {title} at {when}."


NATIVE_TOOLS: list[ToolSpec] = [
    ToolSpec(
        name="get_current_time",
        description="Get the current date and time",
        parameters={
            "type": "object",
            "properties": {},
            "additionalProperties": False,
        },
    ),
    ToolSpec(
        name="get_cpu_usage",
        description="Get current CPU usage percentage",
        parameters={
            "type": "object",
            "properties": {},
            "additionalProperties": False,
        },
    ),
    ToolSpec(
        name="get_memory_usage",
        description="Get current RAM usage",
        parameters={
            "type": "object",
            "properties": {},
            "additionalProperties": False,
        },
    ),
    ToolSpec(
        name="get_battery",
        description="Get battery level and power state",
        parameters={
            "type": "object",
            "properties": {},
            "additionalProperties": False,
        },
    ),
    ToolSpec(
        name="open_url",
        description="Open a URL in the default web browser",
        parameters={
            "type": "object",
            "properties": {"url": {"type": "string", "description": "http(s) URL"}},
            "required": ["url"],
            "additionalProperties": False,
        },
    ),
    ToolSpec(
        name="search_web",
        description="Search the web and return top result titles and links",
        parameters={
            "type": "object",
            "properties": {
                "query": {"type": "string"},
                "max_results": {"type": "integer"},
            },
            "required": ["query"],
            "additionalProperties": False,
        },
    ),
    ToolSpec(
        name="launch_app",
        description="Launch an application by path or command line",
        parameters={
            "type": "object",
            "properties": {"app": {"type": "string", "description": "exe path or command"}},
            "required": ["app"],
            "additionalProperties": False,
        },
    ),
    ToolSpec(
        name="set_reminder",
        description="Store a reminder for later",
        parameters={
            "type": "object",
            "properties": {
                "title": {"type": "string"},
                "when": {"type": "string", "description": "ISO datetime or natural time"},
            },
            "required": ["title"],
            "additionalProperties": False,
        },
    ),
]


class NativeToolRunner:
    def __init__(self, data_dir: Path) -> None:
        self.data_dir = Path(data_dir)

    def specs(self) -> list[ToolSpec]:
        return list(NATIVE_TOOLS)

    async def run(self, name: str, arguments: dict) -> str:
        coro = _dispatch(name, arguments, self.data_dir)
        try:
            if coro is None:
                return f"Unknown tool: {name}"
            text = await coro
            return str(text)
        except Exception as exc:  # noqa: BLE001
            logger.exception("tool %s failed", name)
            return f"Tool {name} error: {exc}"


def _dispatch(name: str, arguments: dict, data_dir: Path):
    if name == "get_current_time":
        return get_current_time(arguments)
    if name == "get_cpu_usage":
        return get_cpu_usage(arguments)
    if name == "get_memory_usage":
        return get_memory_usage(arguments)
    if name == "get_battery":
        return get_battery(arguments)
    if name == "open_url":
        return open_url(arguments)
    if name == "search_web":
        return search_web(arguments)
    if name == "launch_app":
        return launch_app(arguments)
    if name == "set_reminder":
        return set_reminder(arguments, data_dir)
    return None
