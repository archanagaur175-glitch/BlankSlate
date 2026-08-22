"""Tests for the centralized bundled-resource resolver (P1).

These assert that every expected bundled asset (STT model, Ollama binary,
wake-word models) resolves through the single ``resolve_bundled_resource``
entry point instead of any ad-hoc path.

When run inside a frozen/installed build, ``test_resolves_actual_bundle`` walks
the real resource tree; otherwise it is skipped so the suite stays green in a
plain source checkout.
"""
from __future__ import annotations

import importlib
import os
import sys
from pathlib import Path

import pytest

import blankslate.resources as rsrc


def _make_fake_bundle(tmp_path: Path) -> Path:
    """Mimic the PyInstaller one-folder layout the spec produces."""
    meipass = tmp_path / "_internal"
    model_dir = meipass / "blankslate" / "resources" / "models" / "faster-whisper-base.en"
    model_dir.mkdir(parents=True)
    (model_dir / "model.bin").write_text("fake")
    (model_dir / "config.json").write_text("{}")
    ow = meipass / "openwakeword" / "resources" / "models"
    ow.mkdir(parents=True)
    (ow / "hey_jarvis_v0.1.onnx").write_text("fake")
    ollama = meipass / "ollama"
    ollama.mkdir()
    (ollama / "ollama.exe").write_text("fake")
    return meipass


def test_resolve_stt_model_bundled(tmp_path: Path, monkeypatch):
    meipass = _make_fake_bundle(tmp_path)
    monkeypatch.setattr(sys, "_MEIPASS", str(meipass), raising=False)
    resolved = rsrc.resolve_stt_model("base.en")
    assert resolved.endswith("faster-whisper-base.en")
    assert os.path.isfile(os.path.join(resolved, "model.bin"))


def test_resolve_stt_model_falls_back_to_hf_name(tmp_path: Path, monkeypatch):
    # No bundle on disk -> return the HuggingFace model name (triggers a download).
    monkeypatch.setattr(sys, "_MEIPASS", str(tmp_path / "empty"), raising=False)
    assert rsrc.resolve_stt_model("base.en") == "base.en"


def test_resolve_ollama_binary_bundled(tmp_path: Path, monkeypatch):
    meipass = _make_fake_bundle(tmp_path)
    monkeypatch.setattr(sys, "_MEIPASS", str(meipass), raising=False)
    binary = rsrc.resolve_ollama_binary()
    assert binary is not None
    assert binary.endswith("ollama.exe")


def test_resolve_wake_models_bundled(tmp_path: Path, monkeypatch):
    meipass = _make_fake_bundle(tmp_path)
    monkeypatch.setattr(sys, "_MEIPASS", str(meipass), raising=False)
    path = rsrc.resolve_bundled_resource(
        "openwakeword", "resources", "models", "hey_jarvis_v0.1.onnx"
    )
    assert path is not None
    assert path.name == "hey_jarvis_v0.1.onnx"


def test_resolves_actual_bundle():
    """Walk a real built/installed bundle if one is discoverable."""
    candidates = [
        os.environ.get("BLANKSLATE_BUNDLE_ROOT"),
        getattr(sys, "_MEIPASS", None),
    ]
    # Installed Windows layout: <app>/resources or <app> root.
    if sys.platform.startswith("win"):
        prog = os.environ.get("ProgramFiles")
        if prog:
            candidates.append(os.path.join(prog, "BlankSlate"))
            candidates.append(os.path.join(prog, "BlankSlate", "resources"))

    for root in candidates:
        if not root or not os.path.isdir(root):
            continue
        model = rsrc.resolve_bundled_resource(
            "blankslate", "resources", "models", "faster-whisper-base.en"
        )
        if model is not None and os.path.isfile(os.path.join(model, "model.bin")):
            assert rsrc.resolve_stt_model("base.en") == str(model)
            return
    pytest.skip("no actual built bundle present in this environment")
