"""Speech-to-text engine abstraction with a faster-whisper implementation."""

from __future__ import annotations

import logging
import os
import sys
from abc import ABC, abstractmethod

import numpy as np

logger = logging.getLogger(__name__)


def _bundled_models_root() -> str:
    """Resolve the directory that holds bundled ML models.

    In the PyInstaller build the models live under ``sys._MEIPASS``; in a source
    checkout they live under ``blankslate/resources/models``. Falling back to a
    HuggingFace model name (which triggers a download) keeps dev workflows working.
    """
    here = os.path.dirname(os.path.abspath(__file__))  # .../blankslate/stt
    pkg_root = os.path.dirname(here)  # .../blankslate
    candidates = []
    meipass = getattr(sys, "_MEIPASS", "")
    if meipass:
        candidates.append(os.path.join(meipass, "blankslate", "resources", "models"))
    candidates.append(os.path.join(pkg_root, "resources", "models"))
    for candidate in candidates:
        if os.path.isdir(candidate):
            return candidate
    return candidates[-1]


def _resolve_whisper_model(model: str) -> str:
    """Return a local model directory when bundled, else the HF model name."""
    local = os.path.join(_bundled_models_root(), f"faster-whisper-{model}")
    if os.path.isdir(local) and os.path.exists(os.path.join(local, "model.bin")):
        return local
    return model


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
        model_ref = _resolve_whisper_model(self.model)
        logger.info("STT loading %s on %s (%s)", model_ref, device, self.compute)
        try:
            self._model = WhisperModel(model_ref, device=device, compute_type=self.compute)
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
