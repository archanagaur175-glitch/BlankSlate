"""Speech-to-text engine abstraction with a faster-whisper implementation."""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod

import numpy as np

logger = logging.getLogger(__name__)


class STTEngine(ABC):
    name: str = "abstract"

    @abstractmethod
    def transcribe(self, audio: np.ndarray, language: str | None = None) -> str:
        """Transcribe mono float32 audio (assumed 16 kHz)."""


def _ctranslate2_cuda_available() -> bool:
    try:
        import ctranslate2

        return bool(ctranslate2.get_cuda_device_count() > 0)
    except Exception:  # noqa: BLE001
        return False


class FasterWhisperEngine(STTEngine):
    """faster-whisper (MIT) transcription on CTranslate2.

    CUDA is used only when explicitly requested *and* a usable CTranslate2
    build with CUDA support is present; otherwise we fall back to CPU int8 so
    the daemon always starts.
    """

    name = "faster-whisper"

    def __init__(self, model: str = "base.en", device: str = "auto", compute: str = "int8") -> None:
        self.model = model
        self.device = device
        self.compute = compute
        self._model: object | None = None

    def _ensure_model(self) -> None:
        if self._model is not None:
            return
        from faster_whisper import WhisperModel

        device = self.device
        if device == "auto":
            device = "cuda" if _ctranslate2_cuda_available() else "cpu"
        self._device = device
        logger.info("STT loading %s on %s (%s)", self.model, device, self.compute)
        try:
            self._model = WhisperModel(self.model, device=device, compute_type=self.compute)
        except Exception as exc:  # noqa: BLE001
            if device != "cpu":
                logger.warning("STT CUDA load failed (%s); falling back to CPU", exc)
                self._device = "cpu"
                self._model = WhisperModel(self.model, device="cpu", compute_type=self.compute)
            else:
                raise

    def transcribe(self, audio: np.ndarray, language: str | None = None) -> str:
        self._ensure_model()
        samples = np.asarray(audio, dtype=np.float32).reshape(-1)
        if samples.size == 0:
            return ""
        try:
            segments, _info = self._model.transcribe(  # type: ignore[union-attr]
                samples, language=language, vad_filter=True
            )
            return " ".join(seg.text.strip() for seg in segments).strip()
        except Exception as exc:  # noqa: BLE001
            if getattr(self, "_device", "cpu") != "cpu" and (
                "cublas" in str(exc).lower() or "cuda" in str(exc).lower()
            ):
                logger.warning("STT CUDA compute failed (%s); rebuilding on CPU", exc)
                self._model = None
                self._device = "cpu"
                return self.transcribe(audio, language=language)
            logger.error("transcription failed: %s", exc)
            return ""


class NullSTTEngine(STTEngine):
    """Empty engine for tests and hardware-less development."""

    name = "null"

    def transcribe(self, audio: np.ndarray, language: str | None = None) -> str:
        return ""


def build_stt_engine(engine: str, model: str, device: str, compute: str) -> STTEngine:
    if engine == "faster-whisper":
        return FasterWhisperEngine(model=model, device=device, compute=compute)
    if engine == "null":
        return NullSTTEngine()
    raise ValueError(f"unknown STT engine: {engine}")
