"""Wake-word engine abstraction plus the openwakeword implementation."""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path

import numpy as np

logger = logging.getLogger(__name__)

BUILTIN_MODELS = ("alexa", "hey_jarvis", "hey_mycroft", "hey_rhasspy")


@dataclass
class WakeDetection:
    label: str
    confidence: float

    def to_dict(self) -> dict:
        return {"label": self.label, "confidence": round(float(self.confidence), 4)}


class WakeEngine(ABC):
    name: str = "abstract"

    @abstractmethod
    def process(self, chunk: np.ndarray) -> list[WakeDetection]:
        """Feed a continuous block of mono float32 audio (any size)."""

    def reset(self) -> None:
        pass


def _wakeword_class():
    from openwakeword import WakeWord

    return WakeWord


class OpenWakeWordEngine(WakeEngine):
    """openwakeword (Apache-2.0) running on ONNX Runtime on Windows.

    The library is unmaintained upstream, so it is isolated behind this engine
    adapter; a drop-in replacement can swap in below without touching callers.
    """

    name = "openwakeword"
    FRAME_SAMPLES = 1280  # 80 ms @ 16 kHz

    def __init__(
        self,
        model: str = "hey_jarvis",
        threshold: float = 0.6,
        trigger_level: int = 1,
    ) -> None:
        self.model = model
        self.threshold = float(threshold)
        self.trigger_level = max(1, int(trigger_level))
        self._ww: object | None = None
        self._frame_buf = np.zeros(0, dtype=np.float32)
        self._hits = 0

    def _ensure_model(self) -> None:
        if self._ww is not None:
            return
        if self.model in BUILTIN_MODELS:
            self._ww = _wakeword_class()(enable=[self.model])
            logger.info("wake engine loaded builtin model %r", self.model)
        elif Path(self.model).exists():
            self._ww = _wakeword_class()(model_paths=[str(self.model)])
            logger.info("wake engine loaded model from %r", self.model)
        else:
            raise FileNotFoundError(f"wake model {self.model!r} not found and not a builtin model")

    def process(self, chunk: np.ndarray) -> list[WakeDetection]:
        if getattr(self, "_broken", False):
            return []
        detections: list[WakeDetection] = []
        try:
            self._ensure_model()
        except Exception as exc:  # noqa: BLE001
            logger.warning("wake model unavailable; disabling wake word: %s", exc)
            self._broken = True
            return []
        try:
            self._frame_buf = np.concatenate(
                [self._frame_buf, np.asarray(chunk, dtype=np.float32).reshape(-1)]
            )
            while self._frame_buf.size >= self.FRAME_SAMPLES:
                frame = self._frame_buf[: self.FRAME_SAMPLES]
                self._frame_buf = self._frame_buf[self.FRAME_SAMPLES :]
                scores = self._ww.predict(frame, threshold=self.threshold)  # type: ignore[union-attr]
                for label, value in self._ephemeral_scores(scores):
                    if value >= self.threshold:
                        self._hits += 1
                        if self._hits >= self.trigger_level:
                            detections.append(WakeDetection(label=label, confidence=value))
                            self._hits = 0
                    else:
                        self._hits = 0
        except Exception as exc:  # noqa: BLE001
            logger.warning("wake prediction error; disabling wake word: %s", exc)
            self._broken = True
            return []
        return detections

    @staticmethod
    def _ephemeral_scores(scores) -> list[tuple[str, float]]:
        """openwakeword 0.6 returns a list of per-frame prediction dicts."""
        out: list[tuple[str, float]] = []
        try:
            for frame in scores:
                for label, value in frame.items():
                    out.append((label, float(value)))
        except (AttributeError, TypeError):  # already a plain dict
            for label, value in scores.items():  # type: ignore[attr-defined]
                out.append((label, float(value)))
        return out

    def reset(self) -> None:
        self._frame_buf = np.zeros(0, dtype=np.float32)
        self._hits = 0
