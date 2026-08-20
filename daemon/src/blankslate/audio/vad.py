"""Abstraction layers over the anti-noise VAD."""

from __future__ import annotations

import numpy as np

try:
    import webrtcvad  # type: ignore

    _HAS_WEBRTC_VAD = True
except Exception:  # pragma: no cover - optional dependency
    _HAS_WEBRTC_VAD = False


def to_pcm16(mono_float32: np.ndarray) -> bytes:
    return (np.clip(mono_float32, -1.0, 1.0) * 32767).astype(np.int16).tobytes()


def rms(mono_float32: np.ndarray) -> float:
    if mono_float32.size == 0:
        return 0.0
    return float(np.sqrt(np.mean(np.square(mono_float32))))


class Vad:
    """Thin wrapper over webrtcvad (frame-based, 10/20/30 ms, mono 16 kHz)."""

    FRAME_MS = 30

    def __init__(self, sample_rate: int = 16000, mode: int = 2) -> None:
        if not _HAS_WEBRTC_VAD:
            raise RuntimeError("webrtcvad is not installed")
        self.sample_rate = sample_rate
        self.frame_len = sample_rate * self.FRAME_MS // 1000
        self._vad = webrtcvad.Vad(mode)  # type: ignore[attr-defined]

    def set_mode(self, mode: int) -> None:
        self._vad.set_mode(mode)

    def is_speech(self, frame_float32: np.ndarray) -> bool:
        frame = np.asarray(frame_float32, dtype=np.float32).reshape(-1)
        if frame.size != self.frame_len:
            if frame.size == 0:
                return False
            frame = np.resize(frame, self.frame_len)
        return bool(self._vad.is_speech(to_pcm16(frame), self.sample_rate))


class EnergyGate:
    """Simple RMS gate used to pre-filter silence cheaply."""

    def __init__(self, threshold: float = 0.004) -> None:
        self.threshold = threshold

    def is_speech(self, frame_float32: np.ndarray) -> bool:
        return rms(frame_float32) >= self.threshold


class UtteranceDetector:
    """Accumulates blocks into one utterance once ``armed``.

    After the wake word fires, the app arms the detector. Blocks keep flowing
    in; once trailing silence reaches ``end_silence_blocks`` or the utterance
    exceeds ``max_blocks``, the collected audio is finalized and returned.
    """

    def __init__(
        self,
        sample_rate: int,
        vad: Vad | None,
        end_silence_ms: int = 700,
        max_utterance_ms: int = 20000,
        block_ms: int = 30,
    ) -> None:
        self.sample_rate = sample_rate
        self._vad = vad
        self._end_blocks = max(1, end_silence_ms // block_ms)
        self._max_blocks = max(1, max_utterance_ms // block_ms)
        self._blocks: list[np.ndarray] = []
        self._silent_after_speech = 0
        self._heard_speech = False
        self.armed = False

    def arm(self) -> None:
        self._blocks.clear()
        self._silent_after_speech = 0
        self._heard_speech = False
        self.armed = True

    def feed(self, frame_float32: np.ndarray, is_speech: bool | None = None) -> np.ndarray | None:
        """Push one block. Returns the final utterance audio, or None.

        ``is_speech`` may override the internal VAD decision (used by tests to
        stay deterministic).
        """
        if not self.armed:
            return None
        frame = np.asarray(frame_float32, dtype=np.float32).reshape(-1)
        self._blocks.append(frame)
        if is_speech is None:
            is_speech = True
            if self._vad is not None:
                is_speech = self._vad.is_speech(frame)
        if is_speech:
            self._heard_speech = True
            self._silent_after_speech = 0
        elif self._heard_speech:
            self._silent_after_speech += 1
        oversized = len(self._blocks) >= self._max_blocks
        if oversized or (self._heard_speech and self._silent_after_speech >= self._end_blocks):
            return self.finalize()
        return None

    def finalize(self) -> np.ndarray | None:
        self.armed = False
        if not self._blocks:
            return None
        audio = np.concatenate(self._blocks)
        self._blocks.clear()
        self._silent_after_speech = 0
        self._heard_speech = False
        return audio
