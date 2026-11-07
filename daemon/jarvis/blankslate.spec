# -*- mode: python ; coding: utf-8 -*-
from PyInstaller.utils.hooks import collect_data_files

datas = []
datas += collect_data_files('jarvis')


a = Analysis(
    ['run_daemon.py'],
    pathex=['.'],
    binaries=[],
    datas=datas,
    hiddenimports=['jarvis.llm', 'jarvis.llm.ollama', 'jarvis.llm.openai', 'jarvis.llm.anthropic', 'jarvis.reply.engine', 'jarvis.reply.planner', 'jarvis.reply.enrichment', 'jarvis.reply.graph_ops', 'jarvis.reply.evaluator', 'jarvis.reply.log_meal', 'jarvis.tools', 'jarvis.db', 'jarvis.speech', 'jarvis.utils'],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='blankslate',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='blankslate',
)
