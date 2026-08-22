"""Single source of truth for resolving bundled on-disk resources.

Different run contexts place resources in different roots:

* PyInstaller one-folder build (``sys._MEIPASS``)
* source checkout (``src/blankslate``)
* installed Windows app (under the app root or a ``resources/`` subdir)

Callers pass the relative path parts for a logical resource; the first existing
candidate wins. This removes the fragile, hard-coded path assumptions that
previously caused bundled assets (STT model, Ollama binary) to be missed.
"""
from __future__ import annotations

import sys
from pathlib import Path


def _candidate_roots() -> list[Path]:
    roots: list[Path] = []
    meipass = getattr(sys, "_MEIPASS", "")
    if meipass:
        roots.append(Path(meipass))
        roots.append(Path(meipass) / "blankslate")
    here = Path(__file__).resolve()  # .../blankslate/resources.py
    pkg_root = here.parent  # .../blankslate
    roots.append(pkg_root)
    roots.append(pkg_root / "resources")
    # Installed app layout: <app>/resources and <app> root.
    exe = Path(sys.executable).resolve()
    roots.append(exe.parent)
    if exe.parent.parent != exe.parent:
        roots.append(exe.parent.parent)
    # De-duplicate while preserving order.
    seen: set[Path] = set()
    out: list[Path] = []
    for root in roots:
        try:
            root = root.resolve()
        except Exception:  # noqa: BLE001
            continue
        if root in seen:
            continue
        seen.add(root)
        out.append(root)
    return out


def resolve_bundled_resource(*parts: str) -> Path | None:
    """Return the first existing path for ``parts`` across candidate roots.

    Returns ``None`` if no candidate exists (callers then fall back to a
    network/model name or raise).
    """
    if not parts:
        return None
    for root in _candidate_roots():
        candidate = root.joinpath(*parts)
        if candidate.exists():
            return candidate
    return None


def resolve_stt_model(model: str) -> str:
    """Return a local STT model directory path, or the HF model name if absent."""
    local = resolve_bundled_resource(
        "blankslate", "resources", "models", f"faster-whisper-{model}"
    )
    if local is not None and local.is_dir() and (local / "model.bin").exists():
        return str(local)
    return model


def resolve_ollama_binary() -> str | None:
    """Locate the bundled (or system) Ollama server executable."""
    name = "ollama.exe" if sys.platform.startswith("win") else "ollama"
    local = resolve_bundled_resource("ollama", name)
    if local is not None:
        return str(local)
    # First-run fetched Ollama lives under the data dir.
    if _OLLAMA_DATA_DIR:
        cand = Path(_OLLAMA_DATA_DIR) / name
        if cand.exists():
            return str(cand)
    # Fall back to a system install on PATH / common locations.
    import shutil

    on_path = shutil.which(name)
    if on_path:
        return on_path
    return None


# Optional extra search root for a first-run-fetched Ollama (set at startup).
_OLLAMA_DATA_DIR: str | None = None


def register_ollama_data_dir(path: str | Path | None) -> None:
    global _OLLAMA_DATA_DIR
    _OLLAMA_DATA_DIR = str(path) if path else None
