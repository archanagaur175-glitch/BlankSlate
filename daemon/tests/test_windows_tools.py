"""Tests for the M5 Windows automation tools.

The Windows-only libraries are mocked so the suite runs on any runner. Each tool
degrades to a string (never raises) when its dependency is missing, which is the
contract the agent loop relies on.
"""

import asyncio
import sys
import tempfile
import types
from pathlib import Path
from unittest.mock import MagicMock, patch

from blankslate.tools import native
from blankslate.tools.windows import (
    get_volume,
    list_directory,
    lock_screen,
    open_file,
    set_brightness,
    set_volume,
    switch_virtual_desktop,
    take_screenshot,
    window_dispatch,
)


def test_native_specs_include_windows_tools():
    runner = native.NativeToolRunner(Path(tempfile.mkdtemp()))
    names = {s.name for s in runner.specs()}
    assert "focus_app" in names
    assert "lock_screen" in names
    assert "set_volume" in names


def test_window_dispatch_unknown_returns_none():
    assert window_dispatch("does_not_exist", {}, None) is None


def test_list_directory_real():
    d = Path(tempfile.mkdtemp())
    (d / "a.txt").write_text("x", encoding="utf-8")
    (d / "sub").mkdir()

    async def run():
        return await list_directory({"path": str(d)})

    out = asyncio.run(run())
    assert "a.txt" in out
    assert "sub" in out


def test_open_file_uses_startfile():
    with patch("os.startfile", MagicMock()) as start:

        async def run():
            return await open_file({"path": "C:\\x.txt"})

        out = asyncio.run(run())
    assert "Opened" in out
    start.assert_called_once_with("C:\\x.txt")


def test_lock_screen_calls_api():
    with patch("ctypes.windll.user32.LockWorkStation", create=True) as lock:

        async def run():
            return await lock_screen({})

        out = asyncio.run(run())
    assert "Locked" in out
    lock.assert_called_once()


def test_take_screenshot_saves():
    class _Img:
        def save(self, p):  # noqa: D401
            self.saved = p

    with patch("PIL.ImageGrab.grab", return_value=_Img()) as grab:
        data = Path(tempfile.mkdtemp())

        async def run():
            return await take_screenshot({}, data)

        out = asyncio.run(run())
    assert "Screenshot saved" in out
    grab.assert_called_once()


def test_switch_virtual_desktop_sends_key():
    with patch("blankslate.tools.windows._send_desktop_key") as send:

        async def run():
            return await switch_virtual_desktop({"direction": "next"})

        asyncio.run(run())
    send.assert_called_once_with("ctrl+win+right")


def test_set_brightness_invokes_powershell():
    proc = MagicMock()
    proc.stdout = ""
    proc.stderr = ""
    with patch("subprocess.run", return_value=proc) as run:

        async def run2():
            return await set_brightness({"level": 40})

        out = asyncio.run(run2())
    assert "Brightness set to 40%" in out
    assert run.called


def test_volume_tools_use_pycaw():
    comtypes = types.ModuleType("comtypes")
    comtypes.CLSCTX_ALL = 1
    pycaw_pkg = types.ModuleType("pycaw")
    pycaw_sub = types.ModuleType("pycaw.pycaw")

    class _Vol:
        def GetMasterVolumeLevelScalar(self):
            return 0.5

        def SetMasterVolumeLevelScalar(self, v, _):
            self.value = v

        def GetMute(self):
            return 0

        def SetMute(self, m, _):
            self.muted = m

    class _Iface:
        def QueryInterface(self, *a):
            return _Vol()

    class _Devices:
        def Activate(self, *a):
            return _Iface()

    class _AU:
        @staticmethod
        def GetSpeakers():
            return _Devices()

    pycaw_sub.AudioUtilities = _AU
    pycaw_sub.IAudioEndpointVolume = type("IAudioEndpointVolume", (), {"_iid_": "x"})
    pycaw_pkg.pycaw = pycaw_sub

    with patch.dict(
        sys.modules,
        {"comtypes": comtypes, "pycaw": pycaw_pkg, "pycaw.pycaw": pycaw_sub},
    ):

        async def run():
            got = await get_volume({})
            await set_volume({"level": 50})
            return got

        out = asyncio.run(run())
    assert "Volume 50%" in out


def test_search_web_falls_back_to_answers():
    class _DDGS:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def atext(self, q, max_results=5):
            return []

        async def aanswers(self, q):
            return [{"text": "The answer is 42"}]

    ddgs_mod = types.ModuleType("ddgs")
    ddgs_mod.DDGS = _DDGS

    with patch.dict(sys.modules, {"ddgs": ddgs_mod}):

        async def run():
            return await native.search_web({"query": "meaning of life"})

        out = asyncio.run(run())
    assert "42" in out
