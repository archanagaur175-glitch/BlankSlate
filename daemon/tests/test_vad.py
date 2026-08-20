import numpy as np
import pytest

from blankslate.audio.vad import EnergyGate, UtteranceDetector, Vad, rms


def test_rms() -> None:
    assert rms(np.zeros(100)) == 0.0
    assert rms(np.ones(10) * 0.5) == pytest.approx(0.5)
    assert rms(np.zeros(0)) == 0.0


def test_energy_gate() -> None:
    gate = EnergyGate(threshold=0.1)
    assert not gate.is_speech(np.zeros(100))
    assert gate.is_speech(np.full(100, 0.3))


def test_vad_heavy_silence() -> None:
    vad = Vad(sample_rate=16000, mode=0)
    assert not vad.is_speech(np.zeros(480))
    assert isinstance(vad.is_speech(np.full(480, 0.02)), bool)


def test_vad_raises_without_webrtcvad(monkeypatch) -> None:
    monkeypatch.setattr("blankslate.audio.vad._HAS_WEBRTC_VAD", False)
    with pytest.raises(RuntimeError):
        Vad(sample_rate=16000)


def test_utterance_detector_short_sentence() -> None:
    sr = 16000
    block = np.ones(sr * 30 // 1000, dtype=np.float32) * 0.1
    silence = np.zeros(block.size, dtype=np.float32)
    det = UtteranceDetector(sr, None, end_silence_ms=300, max_utterance_ms=3000, block_ms=30)
    assert det.feed(silence, is_speech=False) is None  # not armed
    det.arm()
    assert det.feed(block, is_speech=True) is None
    assert det.feed(block, is_speech=True) is None
    # 10 blocks of silence = 300ms -> finalize
    result = None
    for _ in range(10):
        result = det.feed(silence, is_speech=False)
        if result is not None:
            break
    assert result is not None
    assert result.size >= 2 * block.size


def test_utterance_detector_max_length() -> None:
    sr = 16000
    block = np.ones(sr * 30 // 1000, dtype=np.float32) * 0.1
    det = UtteranceDetector(sr, None, end_silence_ms=5000, max_utterance_ms=120, block_ms=30)
    det.arm()
    for _ in range(10):
        out = det.feed(block, is_speech=True)
        if out is not None:
            break
    assert out is not None and out.size == 4 * block.size  # capped at max_utterance_ms


def test_utterance_detector_finalize() -> None:
    sr = 16000
    block = np.ones(sr * 30 // 1000, dtype=np.float32)
    det = UtteranceDetector(sr, None, end_silence_ms=1000, max_utterance_ms=3000, block_ms=30)
    det.arm()
    det.feed(block, is_speech=True)
    out = det.finalize()
    assert out is not None
    assert out.size == block.size
    assert not det.armed
