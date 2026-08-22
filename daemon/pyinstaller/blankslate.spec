# -*- mode: python ; coding: utf-8 -*-
"""Freeze the BlankSlate daemon into a standalone, distributable folder.

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
SRC = os.path.join(DAEMON_ROOT, "src")

# The daemon imports its heavy ML dependencies lazily at runtime, so PyInstaller
# cannot discover them from a static scan. Collect them explicitly. Kokoro/Torch
# are excluded on purpose; the daemon falls back to the offline Windows SAPI
# voice when they are absent, keeping the bundle lean.
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
    "ddgs",
    "mcp",
    "httpx",
    "anyio",
]

datas = []
binaries = []
hiddenimports = list(collect_submodules("blankslate"))
for pkg in BUNDLE_PACKAGES:
    try:
        d, b, h = collect_all(pkg)
    except Exception as exc:  # noqa: BLE001
        print(f"warning: could not collect {pkg}: {exc}")
        continue
    datas.extend(d)
    binaries.extend(b)
    hiddenimports.extend(h)

# Bundle local ML models so the daemon is fully offline (no HuggingFace/GitHub
# downloads at runtime, which are unreliable behind the frozen interpreter).
# The STT model is placed under blankslate/resources/models and the openwakeword
# models under openwakeword/resources/models to match the paths the libraries
# resolve at runtime. build_daemon.ps1 populates DAEMON_ROOT/models beforehand.
MODELS_SRC = os.path.join(DAEMON_ROOT, "models")
if os.path.isdir(MODELS_SRC):
    stt_models = os.path.join(MODELS_SRC, "faster-whisper-base.en")
    if os.path.isdir(stt_models):
        datas.append((stt_models, "blankslate/resources/models/faster-whisper-base.en"))
    ow_models = os.path.join(MODELS_SRC, "openwakeword")
    if os.path.isdir(ow_models):
        datas.append((ow_models, "openwakeword/resources/models"))
else:
    print("warning: daemon/models not found; models will be downloaded at runtime (may fail)")

a = Analysis(
    [os.path.join(SRC, "blankslate", "__main__.py")],
    pathex=[SRC],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    runtime_hooks=[],
    excludes=["PyQt5", "PyQt6", "tkinter", "torch", "kokoro", "misaki", "transformers"],
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
