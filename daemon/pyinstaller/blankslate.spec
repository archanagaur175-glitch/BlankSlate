# -*- mode: python ; coding: utf-8 -*-
"""Freeze the BlankSlate daemon (vendored isair/jarvis fork) into a standalone folder.

Run from the ``daemon/`` directory:

    pyinstaller pyinstaller/blankslate.spec --noconfirm --clean

Output lands in ``dist/BlankslateDaemon/`` and is copied into the HUD's bundled
resources by ``build_daemon.ps1`` (used by the release workflow) so the installer
ships a self-contained, offline-capable assistant.
"""

import os
import sys

from PyInstaller.utils.hooks import collect_all, collect_submodules

# PyInstaller executes this spec without defining ``__file__``, so locate the
# spec from the command line argument and walk up to the daemon root.
SPEC_PATH = next((a for a in sys.argv if a.endswith(".spec")), None)
if SPEC_PATH:
    DAEMON_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(SPEC_PATH)))
else:
    DAEMON_ROOT = os.getcwd()

# The vendored jarvis package lives at <DAEMON_ROOT>/jarvis/jarvis; its parent
# (<DAEMON_ROOT>/jarvis) is what needs to be importable as ``jarvis``.
JARVIS_PARENT = os.path.join(DAEMON_ROOT, "jarvis")
if JARVIS_PARENT not in sys.path:
    sys.path.insert(0, JARVIS_PARENT)

ENTRY = os.path.join(JARVIS_PARENT, "run_blankslate.py")

# The daemon imports its heavy ML dependencies lazily at runtime, so PyInstaller
# cannot discover them from a static scan. Collect them explicitly. Kokoro/Torch
# are excluded on purpose: TTS is disabled in the bundled config and the
# Chatterbox backend imports torch lazily, so the bundle stays lean and torch-free.
BUNDLE_PACKAGES = [
    "faster_whisper",
    "ctranslate2",
    "huggingface_hub",
    "tokenizers",
    "onnxruntime",
    "openwakeword",
    "sounddevice",
    "webrtcvad",
    "pycaw",
    "pywin32",
    "comtypes",
    "pywinauto",
    "Pillow",
    "psutil",
    "mcp",
    "httpx",
    "anyio",
    "pynput",
    "pygame",
    "rapidfuzz",
    "pytesseract",
    "geoip2",
    "miniupnpc",
    "faiss",
    "bs4",
    "html2text",
    "websockets",
    "python-dotenv",
    "requests",
]

datas = []
binaries = []
hiddenimports = []
for pkg in BUNDLE_PACKAGES:
    try:
        d, b, h = collect_all(pkg)
    except Exception as exc:  # noqa: BLE001
        print(f"warning: could not collect {pkg}: {exc}")
        continue
    datas.extend(d)
    binaries.extend(b)
    hiddenimports.extend(h)

# Bundle every first-party jarvis submodule except the PyQt6 desktop app, which
# is not used by the headless daemon and would pull in the entire Qt stack.
hiddenimports += [
    m for m in collect_submodules("jarvis")
    if not m.startswith("jarvis.desktop_app")
]

a = Analysis(
    [ENTRY],
    pathex=[JARVIS_PARENT],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    runtime_hooks=[],
    excludes=[
        "PyQt6", "PyQt6-WebEngine", "PyQt5", "tkinter",
        "torch", "kokoro", "misaki", "transformers", "chatterbox",
        "playwright", "flask",
    ],
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="blankslate",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name="BlankslateDaemon",
)
