"""Deep Windows automation tools (M5).

Every Windows-only dependency is imported lazily inside the function that needs
it, so importing this module never fails on a machine missing the library or on
non-Windows hosts. Each tool degrades gracefully to a human-readable message
instead of raising, because the agent loop treats a raised exception as a tool
error but a returned string is just another observation.
"""

from __future__ import annotations

import datetime
import logging
import os
import subprocess
from pathlib import Path

import psutil

from blankslate.router.tool_router import ToolSpec

logger = logging.getLogger(__name__)

SW_RESTORE = 9
SW_MINIMIZE = 6
SW_MAXIMIZE = 3


# ------------------------------------------------------------- window helpers


def _visible_windows():
    import win32gui

    out: list[tuple[int, str]] = []

    def cb(hwnd, _):  # noqa: ANN001
        if win32gui.IsWindowVisible(hwnd):
            title = win32gui.GetWindowText(hwnd)
            if title:
                out.append((hwnd, title))

    win32gui.EnumWindows(cb, None)
    return out


def _pid_of(hwnd: int) -> int:
    import win32process

    return win32process.GetWindowThreadProcessId(hwnd)[1]


def _exe_of(pid: int) -> str:
    try:
        return psutil.Process(pid).name()
    except Exception:  # noqa: BLE001
        return ""


def _match_window(app: str):
    app = (app or "").lower()
    for hwnd, title in _visible_windows():
        pid = _pid_of(hwnd)
        exe = _exe_of(pid).lower()
        if app in title.lower() or (exe and app in exe):
            return hwnd, title
    return None, None


# ------------------------------------------------------------------ app tools


async def list_running_apps(arguments: dict, data_dir: Path | None = None) -> str:
    try:
        seen: set[str] = set()
        lines: list[str] = []
        for hwnd, title in _visible_windows():
            exe = _exe_of(_pid_of(hwnd))
            key = exe or title
            if key in seen:
                continue
            seen.add(key)
            lines.append(f"{title}  ({exe})")
        return "\n".join(lines[:50]) or "No application windows found."
    except Exception as exc:  # noqa: BLE001
        return f"list failed: {exc}"


async def focus_app(arguments: dict, data_dir: Path | None = None) -> str:
    app = str(arguments.get("app") or "").strip()
    if not app:
        return "Result: missing app name"
    try:
        import win32gui

        hwnd, title = _match_window(app)
        if hwnd is None:
            return f"No running window matched {app!r}."
        win32gui.ShowWindow(hwnd, SW_RESTORE)
        win32gui.SetForegroundWindow(hwnd)
        return f"Focused {title}."
    except Exception as exc:  # noqa: BLE001
        return f"focus failed: {exc}"


async def close_app(arguments: dict, data_dir: Path | None = None) -> str:
    app = str(arguments.get("app") or "").strip()
    if not app:
        return "Result: missing app name"
    try:
        import win32con
        import win32gui

        hwnd, title = _match_window(app)
        if hwnd is None:
            return f"No running window matched {app!r}."
        win32gui.PostMessage(hwnd, win32con.WM_CLOSE, 0, 0)
        try:
            psutil.Process(_pid_of(hwnd)).terminate()
        except Exception:  # noqa: BLE001
            pass
        return f"Closed {title}."
    except Exception as exc:  # noqa: BLE001
        return f"close failed: {exc}"


async def minimize_app(arguments: dict, data_dir: Path | None = None) -> str:
    app = str(arguments.get("app") or "").strip()
    if not app:
        return "Result: missing app name"
    try:
        import win32gui

        hwnd, title = _match_window(app)
        if hwnd is None:
            return f"No running window matched {app!r}."
        win32gui.ShowWindow(hwnd, SW_MINIMIZE)
        return f"Minimized {title}."
    except Exception as exc:  # noqa: BLE001
        return f"minimize failed: {exc}"


async def maximize_app(arguments: dict, data_dir: Path | None = None) -> str:
    app = str(arguments.get("app") or "").strip()
    if not app:
        return "Result: missing app name"
    try:
        import win32gui

        hwnd, title = _match_window(app)
        if hwnd is None:
            return f"No running window matched {app!r}."
        win32gui.ShowWindow(hwnd, SW_MAXIMIZE)
        return f"Maximized {title}."
    except Exception as exc:  # noqa: BLE001
        return f"maximize failed: {exc}"


async def snap_window(arguments: dict, data_dir: Path | None = None) -> str:
    app = str(arguments.get("app") or "").strip()
    side = str(arguments.get("side") or "left").lower()
    if not app:
        return "Result: missing app name"
    try:
        import win32api
        import win32gui

        hwnd, title = _match_window(app)
        if hwnd is None:
            return f"No running window matched {app!r}."
        monitor = win32api.MonitorFromWindow(hwnd)
        info = win32api.GetMonitorInfo(monitor)
        left, top, right, bottom = info["Work"]
        width = (right - left) // 2
        height = bottom - top
        if side == "right":
            x = left + width
        else:
            x = left
        win32gui.MoveWindow(hwnd, x, top, width, height, True)
        return f"Snapped {title} to the {side} half."
    except Exception as exc:  # noqa: BLE001
        return f"snap failed: {exc}"


def _send_desktop_key(combo: str) -> None:
    import keyboard

    keyboard.send(combo)


async def switch_virtual_desktop(arguments: dict, data_dir: Path | None = None) -> str:
    direction = str(arguments.get("direction") or "next").lower()
    combo = "ctrl+win+right" if direction == "next" else "ctrl+win+left"
    try:
        _send_desktop_key(combo)
        return f"Switched virtual desktop {direction}."
    except Exception as exc:  # noqa: BLE001
        return f"switch failed: {exc}"


# ----------------------------------------------------------------- audio/tools


def _master_volume():
    from comtypes import CLSCTX_ALL
    from pycaw.pycaw import AudioUtilities, IAudioEndpointVolume

    devices = AudioUtilities.GetSpeakers()
    interface = devices.Activate(IAudioEndpointVolume._iid_, CLSCTX_ALL, None)
    return interface.QueryInterface(IAudioEndpointVolume)


async def get_volume(arguments: dict, data_dir: Path | None = None) -> str:
    try:
        volume = _master_volume()
        return f"Volume {int(volume.GetMasterVolumeLevelScalar() * 100)}%"
    except Exception as exc:  # noqa: BLE001
        return f"volume read failed: {exc}"


async def set_volume(arguments: dict, data_dir: Path | None = None) -> str:
    try:
        level = int(arguments.get("level") or 0)
    except (TypeError, ValueError):
        return "Result: level must be an integer 0-100"
    level = max(0, min(100, level))
    try:
        volume = _master_volume()
        volume.SetMasterVolumeLevelScalar(level / 100.0, None)
        return f"Volume set to {level}%."
    except Exception as exc:  # noqa: BLE001
        return f"volume set failed: {exc}"


async def toggle_mute(arguments: dict, data_dir: Path | None = None) -> str:
    try:
        volume = _master_volume()
        muted = bool(volume.GetMute())
        volume.SetMute(0 if muted else 1, None)
        return "Unmuted." if muted else "Muted."
    except Exception as exc:  # noqa: BLE001
        return f"mute toggle failed: {exc}"


def _run_powershell(script: str) -> str:
    res = subprocess.run(
        ["powershell", "-NoProfile", "-Command", script],
        capture_output=True,
        text=True,
        timeout=15,
    )
    return (res.stdout or res.stderr).strip()


async def get_brightness(arguments: dict, data_dir: Path | None = None) -> str:
    try:
        out = _run_powershell(
            "(Get-WmiObject -Namespace root\\wmi -Class WmiMonitorBrightness).CurrentBrightness"
        )
        level = int(str(out).strip().splitlines()[0])
        return f"Brightness {level}%"
    except Exception as exc:  # noqa: BLE001
        return f"brightness read failed: {exc}"


async def set_brightness(arguments: dict, data_dir: Path | None = None) -> str:
    try:
        level = int(arguments.get("level") or 0)
    except (TypeError, ValueError):
        return "Result: level must be an integer 0-100"
    level = max(0, min(100, level))
    try:
        _run_powershell(
            f"(Get-WmiObject -Namespace root\\wmi -Class WmiMonitorBrightnessMethods)"
            f".WmiSetBrightness(1, {level})"
        )
        return f"Brightness set to {level}%."
    except Exception as exc:  # noqa: BLE001
        return f"brightness set failed: {exc}"


# ---------------------------------------------------------- system / files


async def lock_screen(arguments: dict, data_dir: Path | None = None) -> str:
    try:
        import ctypes

        ctypes.windll.user32.LockWorkStation()
        return "Locked the screen."
    except Exception as exc:  # noqa: BLE001
        return f"lock failed: {exc}"


async def take_screenshot(arguments: dict, data_dir: Path | None = None) -> str:
    try:
        from PIL import ImageGrab
    except Exception as exc:  # noqa: BLE001
        return f"screenshot unavailable: {exc}"
    base = Path(data_dir) if data_dir else Path.home()
    out = base / "screenshots"
    out.mkdir(parents=True, exist_ok=True)
    fname = datetime.datetime.now().strftime("%Y-%m-%d_%H%M%S") + ".png"
    path = out / fname
    try:
        img = ImageGrab.grab()
        img.save(path)
        return f"Screenshot saved to {path}"
    except Exception as exc:  # noqa: BLE001
        return f"screenshot failed: {exc}"


async def list_directory(arguments: dict, data_dir: Path | None = None) -> str:
    path = str(arguments.get("path") or (data_dir or "")).strip()
    if not path:
        return "Result: missing path"
    p = Path(path)
    if not p.exists():
        return f"Path not found: {path}"
    if not p.is_dir():
        return f"Not a directory: {path}"
    try:
        items = sorted(p.iterdir(), key=lambda c: (not c.is_dir(), c.name.lower()))
        lines = [(("📁 " if c.is_dir() else "📄 ") + c.name) for c in items[:100]]
        return "\n".join(lines) or "Empty directory."
    except Exception as exc:  # noqa: BLE001
        return f"list failed: {exc}"


async def open_file(arguments: dict, data_dir: Path | None = None) -> str:
    path = str(arguments.get("path") or "").strip()
    if not path:
        return "Result: missing path"
    try:
        os.startfile(path)  # type: ignore[attr-defined]
        return f"Opened {path}."
    except Exception as exc:  # noqa: BLE001
        return f"open failed: {exc}"


WINDOW_TOOLS: list[ToolSpec] = [
    ToolSpec(
        name="list_running_apps",
        description="List the visible application windows currently running",
        parameters={"type": "object", "properties": {}, "additionalProperties": False},
    ),
    ToolSpec(
        name="focus_app",
        description="Bring an application window to the foreground by name",
        parameters={
            "type": "object",
            "properties": {"app": {"type": "string", "description": "app or window name"}},
            "required": ["app"],
            "additionalProperties": False,
        },
    ),
    ToolSpec(
        name="close_app",
        description="Close an application window by name",
        parameters={
            "type": "object",
            "properties": {"app": {"type": "string"}},
            "required": ["app"],
            "additionalProperties": False,
        },
    ),
    ToolSpec(
        name="minimize_app",
        description="Minimize an application window by name",
        parameters={
            "type": "object",
            "properties": {"app": {"type": "string"}},
            "required": ["app"],
            "additionalProperties": False,
        },
    ),
    ToolSpec(
        name="maximize_app",
        description="Maximize an application window by name",
        parameters={
            "type": "object",
            "properties": {"app": {"type": "string"}},
            "required": ["app"],
            "additionalProperties": False,
        },
    ),
    ToolSpec(
        name="snap_window",
        description="Snap an application window to the left or right half of its monitor",
        parameters={
            "type": "object",
            "properties": {
                "app": {"type": "string"},
                "side": {"type": "string", "enum": ["left", "right"]},
            },
            "required": ["app"],
            "additionalProperties": False,
        },
    ),
    ToolSpec(
        name="switch_virtual_desktop",
        description="Switch to the next or previous virtual desktop",
        parameters={
            "type": "object",
            "properties": {"direction": {"type": "string", "enum": ["next", "previous"]}},
            "additionalProperties": False,
        },
    ),
    ToolSpec(
        name="get_volume",
        description="Get the current system master volume",
        parameters={"type": "object", "properties": {}, "additionalProperties": False},
    ),
    ToolSpec(
        name="set_volume",
        description="Set the system master volume (0-100)",
        parameters={
            "type": "object",
            "properties": {"level": {"type": "integer"}},
            "required": ["level"],
            "additionalProperties": False,
        },
    ),
    ToolSpec(
        name="toggle_mute",
        description="Mute or unmute the system audio",
        parameters={"type": "object", "properties": {}, "additionalProperties": False},
    ),
    ToolSpec(
        name="get_brightness",
        description="Get the current screen brightness",
        parameters={"type": "object", "properties": {}, "additionalProperties": False},
    ),
    ToolSpec(
        name="set_brightness",
        description="Set the screen brightness (0-100)",
        parameters={
            "type": "object",
            "properties": {"level": {"type": "integer"}},
            "required": ["level"],
            "additionalProperties": False,
        },
    ),
    ToolSpec(
        name="lock_screen",
        description="Lock the Windows session",
        parameters={"type": "object", "properties": {}, "additionalProperties": False},
    ),
    ToolSpec(
        name="take_screenshot",
        description="Capture a screenshot and save it to the data directory",
        parameters={"type": "object", "properties": {}, "additionalProperties": False},
    ),
    ToolSpec(
        name="list_directory",
        description="List files and folders in a directory",
        parameters={
            "type": "object",
            "properties": {"path": {"type": "string"}},
            "additionalProperties": False,
        },
    ),
    ToolSpec(
        name="open_file",
        description="Open a file or folder with its default application",
        parameters={
            "type": "object",
            "properties": {"path": {"type": "string"}},
            "required": ["path"],
            "additionalProperties": False,
        },
    ),
]


def window_dispatch(name: str, arguments: dict, data_dir: Path | None = None):
    mapping = {
        "list_running_apps": list_running_apps,
        "focus_app": focus_app,
        "close_app": close_app,
        "minimize_app": minimize_app,
        "maximize_app": maximize_app,
        "snap_window": snap_window,
        "switch_virtual_desktop": switch_virtual_desktop,
        "get_volume": get_volume,
        "set_volume": set_volume,
        "toggle_mute": toggle_mute,
        "get_brightness": get_brightness,
        "set_brightness": set_brightness,
        "lock_screen": lock_screen,
        "take_screenshot": take_screenshot,
        "list_directory": list_directory,
        "open_file": open_file,
    }
    func = mapping.get(name)
    if func is None:
        return None
    return func(arguments, data_dir)
