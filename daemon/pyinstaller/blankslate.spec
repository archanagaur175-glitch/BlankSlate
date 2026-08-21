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

from PyInstaller.utils.hooks import collect_submodules

# PyInstaller executes this spec without defining ``__file__``, so locate the
# spec from the command line argument and walk up to the daemon root.
SPEC_PATH = next((a for a in sys.argv if a.endswith(".spec")), None)
if SPEC_PATH:
    DAEMON_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(SPEC_PATH)))
else:
    DAEMON_ROOT = os.getcwd()
SRC = os.path.join(DAEMON_ROOT, "src")

hiddenimports = collect_submodules("blankslate")

a = Analysis(
    [os.path.join(SRC, "blankslate", "__main__.py")],
    pathex=[SRC],
    binaries=[],
    datas=[],
    hiddenimports=hiddenimports,
    hookspath=[],
    runtime_hooks=[],
    excludes=["PyQt5", "PyQt6", "tkinter"],
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
