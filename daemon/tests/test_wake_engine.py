import numpy as np
import pytest

import blankslate.wake.openwakeword_engine as wm


class FakeWakeWord:
    def __init__(self, enable=None, model_paths=None) -> None:
        self.enable = enable
        self.model_paths = model_paths

    def predict(self, frame, threshold=0.5):
        return [{"hey_jarvis": 0.9}]


def test_builtin_model_detection(monkeypatch) -> None:
    monkeypatch.setattr(wm, "_wakeword_class", lambda: FakeWakeWord)
    engine = wm.OpenWakeWordEngine(model="hey_jarvis", threshold=0.5, trigger_level=1)
    dets = engine.process(np.zeros(wm.OpenWakeWordEngine.FRAME_SAMPLES, dtype=np.float32))
    assert len(dets) == 1
    assert dets[0].label == "hey_jarvis"
    assert dets[0].confidence == pytest.approx(0.9)


def test_trigger_level_requires_twice(monkeypatch) -> None:
    monkeypatch.setattr(wm, "_wakeword_class", lambda: FakeWakeWord)
    engine = wm.OpenWakeWordEngine(model="hey_jarvis", threshold=0.5, trigger_level=2)
    frame = np.zeros(wm.OpenWakeWordEngine.FRAME_SAMPLES, dtype=np.float32)
    assert engine.process(frame) == []
    dets = engine.process(frame)
    assert len(dets) == 1


def test_missing_model_file_raises(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(wm, "_wakeword_class", lambda: FakeWakeWord)
    engine = wm.OpenWakeWordEngine(model=str(tmp_path / "missing.onnx"), threshold=0.5)
    with pytest.raises(FileNotFoundError):
        engine.process(np.zeros(1280, dtype=np.float32))


def test_chunk_pieces_accumulate_into_frames(monkeypatch) -> None:
    calls: list[int] = []

    class RecordingWakeWord(FakeWakeWord):
        def predict(self, frame, threshold=0.5):
            calls.append(frame.size)
            return [{"hey_jarvis": 0.0}]

    monkeypatch.setattr(wm, "_wakeword_class", lambda: RecordingWakeWord)
    engine = wm.OpenWakeWordEngine(model="hey_jarvis", threshold=0.5, trigger_level=1)
    engine.process(np.zeros(500, dtype=np.float32))
    engine.process(np.zeros(500, dtype=np.float32))
    engine.process(np.zeros(500, dtype=np.float32))
    assert sum(calls) == 1280  # exactly one full frame produced


def test_reset_clears_frame_buffer(monkeypatch) -> None:
    monkeypatch.setattr(wm, "_wakeword_class", lambda: FakeWakeWord)
    engine = wm.OpenWakeWordEngine(model="hey_jarvis", threshold=0.5, trigger_level=1)
    engine.process(np.zeros(500, dtype=np.float32))
    engine.reset()
    assert engine._frame_buf.size == 0
