import sys
import types
from types import SimpleNamespace

import numpy as np

from blankslate.stt.engine import FasterWhisperEngine, NullSTTEngine, build_stt_engine


def _install_fake_faster_whisper(monkeypatch) -> None:
    fake = types.ModuleType("faster_whisper")

    class FakeModel:
        def __init__(self, model, device, compute_type) -> None:
            self.model = model
            self.device = device

        def transcribe(self, audio, language=None, vad_filter=True):
            return iter([SimpleNamespace(text=" hello world ", start=0.0, end=1.0)]), None

    fake.WhisperModel = FakeModel
    monkeypatch.setitem(sys.modules, "faster_whisper", fake)


def test_faster_whisper_transcribe_cpu(monkeypatch) -> None:
    _install_fake_faster_whisper(monkeypatch)
    monkeypatch.setattr("blankslate.stt.engine._ctranslate2_cuda_available", lambda: False)
    engine = FasterWhisperEngine(model="base.en", device="cpu")
    text = engine.transcribe(np.zeros(1600, dtype=np.float32))
    assert text == "hello world"


def test_auto_device_selects_cpu_when_no_cuda(monkeypatch) -> None:
    _install_fake_faster_whisper(monkeypatch)
    monkeypatch.setattr("blankslate.stt.engine._ctranslate2_cuda_available", lambda: False)
    engine = FasterWhisperEngine(model="base.en", device="auto")
    engine._ensure_model()
    assert engine._model.device == "cpu"  # type: ignore[union-attr]


def test_auto_device_selects_cuda_when_available(monkeypatch) -> None:
    _install_fake_faster_whisper(monkeypatch)

    class FakeCT2:
        @staticmethod
        def get_cuda_device_count():
            return 1

    fake_ct2 = types.ModuleType("ctranslate2")
    fake_ct2.get_cuda_device_count = FakeCT2.get_cuda_device_count
    monkeypatch.setitem(sys.modules, "ctranslate2", fake_ct2)
    engine = FasterWhisperEngine(model="base.en", device="auto")
    engine._ensure_model()
    assert engine._model.device == "cuda"  # type: ignore[union-attr]


def test_empty_audio_returns_empty(monkeypatch) -> None:
    _install_fake_faster_whisper(monkeypatch)
    monkeypatch.setattr("blankslate.stt.engine._ctranslate2_cuda_available", lambda: False)
    engine = FasterWhisperEngine(model="base.en", device="cpu")
    assert engine.transcribe(np.zeros(0, dtype=np.float32)) == ""


def test_null_engine() -> None:
    engine = NullSTTEngine()
    assert engine.transcribe(np.zeros(100)) == ""


def test_factory() -> None:
    assert build_stt_engine("null", "", "", "").name == "null"
    assert build_stt_engine("faster-whisper", "base.en", "cpu", "int8").name == "faster-whisper"
