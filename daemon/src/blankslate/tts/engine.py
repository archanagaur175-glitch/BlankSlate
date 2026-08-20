"""Text-to-speech engines.

Primary: Kokoro-82M (Apache-2.0 weights + MIT-ish pipeline). Fallback: the
Windows-native SAPI voices via comtypes (zero third-party model, always
available offline). Both implement ``TTSEngine.speak``.
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod

import numpy as np

from blankslate.audio.io import Speaker

logger = logging.getLogger(__name__)


class TTSEngine(ABC):
    name: str = "abstract"

    @abstractmethod
    def speak(self, text: str) -> None:
        """Synthesize and play ``text`` (blocking; call from a worker thread)."""

    def available(self) -> bool:
        return True


class KokoroEngine(TTSEngine):
    """Kokoro-82M neural TTS (Apache-2.0). Requires the ``tts-kokoro`` extra.

    espeak-ng (GPL-3.0) is used by the phonemizer only as an external system
    program; BlankSlate never imports or links it.
    """

    name = "kokoro"
    SAMPLE_RATE = 24000

    def __init__(self, speaker: Speaker, voice: str = "af_heart", speed: float = 1.0) -> None:
        self._speaker = speaker
        self.voice = voice
        self.speed = speed
        self._pipeline: object | None = None
        self._import_error: Exception | None = None

    def available(self) -> bool:
        if self._import_error:
            return False
        try:
            import kokoro  # noqa: F401
            import misaki  # noqa: F401
            import torch  # noqa: F401
        except Exception as exc:  # noqa: BLE001
            self._import_error = exc
            return False
        return True

    def _ensure_pipeline(self) -> None:
        if self._pipeline is not None:
            return
        try:
            from kokoro import KPipeline

            self._pipeline = KPipeline(lang_code="a")  # English
        except Exception as exc:  # noqa: BLE001
            self._import_error = exc
            raise RuntimeError(f"kokoro TTS unavailable: {exc}") from exc

    def synthesize(self, text: str) -> np.ndarray:
        self._ensure_pipeline()
        chunks: list[np.ndarray] = []
        for _, _, audio_tensor in self._pipeline(  # type: ignore[union-attr]
            text, voice=self.voice, speed=self.speed
        ):
            audio = audio_tensor.numpy()
            chunks.append(np.asarray(audio, dtype=np.float32).reshape(-1))
        if not chunks:
            return np.zeros(0, dtype=np.float32)
        return np.concatenate(chunks)

    def speak(self, text: str) -> None:
        if not text:
            return
        audio = self.synthesize(text)
        if audio.size:
            self._speaker.play(audio, self.SAMPLE_RATE)


class SapiEngine(TTSEngine):
    """Windows-native SAPI voices via comtypes (offline, zero downloads)."""

    name = "sapi"

    def __init__(self, speaker: Speaker) -> None:
        self._speaker = speaker
        self._voice = None

    def available(self) -> bool:
        try:
            import comtypes  # noqa: F401

            return True
        except Exception:  # noqa: BLE001
            return False

    def _ensure_voice(self):
        if self._voice is not None:
            return self._voice
        import comtypes.client

        voice = comtypes.client.CreateObject("SAPI.SpVoice")
        self._voice = voice
        return voice

    def speak(self, text: str) -> None:
        if not text:
            return
        try:
            voice = self._ensure_voice()
            # 1 = SVSFDefault; async flag is set by SpVoice itself, call is
            # blocking per utterance which keeps ordering simple.
            voice.Speak(text, 1)
        except Exception as exc:  # noqa: BLE001
            logger.warning("SAPI TTS failed: %s", exc)


def build_tts_engine(engine: str, speaker: Speaker, voice: str, speed: float) -> TTSEngine:
    if engine == "kokoro":
        kokoro_engine = KokoroEngine(speaker=speaker, voice=voice, speed=speed)
        if kokoro_engine.available():
            return kokoro_engine
        logger.warning(
            "kokoro TTS unavailable (%s); falling back to SAPI", kokoro_engine._import_error
        )
        return SapiEngine(speaker=speaker)
    if engine == "sapi":
        return SapiEngine(speaker=speaker)
    if engine == "none":
        return _NullTTSEngine()
    raise ValueError(f"unknown TTS engine: {engine}")


class _NullTTSEngine(TTSEngine):
    name = "none"

    def speak(self, text: str) -> None:
        pass
