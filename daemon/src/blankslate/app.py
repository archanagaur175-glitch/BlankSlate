"""BlankSlate daemon application.

Owns the audio pipeline (mic -> VAD -> wake word -> STT -> TTS), the IPC
server, and the request lifecycle. Everything not available on the current
machine is degraded gracefully so the daemon always starts and serves the HUD.
"""

from __future__ import annotations

import asyncio
import logging
import time

import numpy as np

from blankslate.audio.io import MicCapture, MicCaptureError, Speaker
from blankslate.audio.ringbuffer import RingBuffer
from blankslate.audio.vad import UtteranceDetector, Vad
from blankslate.config import DaemonConfig
from blankslate.ipc.server import IpcServer
from blankslate.stt.engine import STTEngine, build_stt_engine
from blankslate.tts.engine import TTSEngine, build_tts_engine
from blankslate.wake import WakeEngine, build_wake_engine

logger = logging.getLogger(__name__)


class DaemonApp:
    def __init__(self, config: DaemonConfig) -> None:
        self.config = config
        self.listening = True
        self._shutdown = asyncio.Event()
        self._ipc = IpcServer(config.ipc.host, config.ipc.port)
        self._speaker = Speaker()
        self._capture: MicCapture | None = None
        self._wake: WakeEngine | None = None
        self._stt: STTEngine | None = None
        self._tts: TTSEngine | None = None
        self._pipeline_task: asyncio.Task | None = None
        self._level_last: float = 0.0

    # ------------------------------------------------------------------ lifecycle

    async def run(self) -> None:
        self.config.ensure_dirs()
        self._ipc.on_message = self._handle_message
        await self._ipc.start()
        self._ipc.write_info_file(self.config.ipc_path())
        await self._ipc.broadcast({"type": "state", "listening": True, "status": "ready"})
        self._start_pipeline()
        logger.info("BlankSlate daemon ready (%s)", self.config.resolved_data_dir())
        try:
            await self._shutdown.wait()
        finally:
            await self._stop()

    async def stop(self) -> None:
        self._shutdown.set()

    async def _stop(self) -> None:
        if self._capture is not None:
            self._capture.stop()
        if self._pipeline_task is not None:
            self._pipeline_task.cancel()
            try:
                await self._pipeline_task
            except asyncio.CancelledError:
                pass
        await self._ipc.stop()

    def _start_pipeline(self) -> None:
        cfg = self.config
        try:
            self._stt = build_stt_engine(
                cfg.stt.engine, cfg.stt.model, cfg.stt.device, cfg.stt.compute
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("STT unavailable: %s", exc)
            self._stt = None
        try:
            self._wake = build_wake_engine(
                cfg.wake.engine, cfg.wake.model, cfg.wake.threshold, cfg.wake.trigger_level
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("wake engine unavailable: %s", exc)
            self._wake = None
        self._tts = build_tts_engine(cfg.tts.engine, self._speaker, cfg.tts.voice, cfg.tts.speed)
        if self._wake is not None and self._stt is not None:
            self._pipeline_task = asyncio.create_task(self._listen_loop())

    # ------------------------------------------------------------------- pipeline

    async def _listen_loop(self) -> None:
        cfg = self.config.audio
        mic = MicCapture(cfg.sample_rate, cfg.channels, cfg.block_ms)
        try:
            mic.start()
        except MicCaptureError as exc:
            logger.error("microphone unavailable; audio pipeline disabled: %s", exc)
            return
        self._capture = mic

        ring = RingBuffer(int(cfg.sample_rate * cfg.ring_seconds))
        try:
            vad = Vad(cfg.sample_rate, cfg.vad_mode)
        except RuntimeError as exc:
            logger.warning("VAD unavailable: %s", exc)
            vad = None
        detector = UtteranceDetector(
            cfg.sample_rate, vad, cfg.end_silence_ms, cfg.max_utterance_ms, cfg.block_ms
        )
        pad_samples = int(cfg.sample_rate * cfg.pre_trigger_pad_ms / 1000)
        pre_trigger: np.ndarray = np.zeros(0, dtype=np.float32)
        state = "wake-listening"
        block = 0

        async def set_status(status: str) -> None:
            await self._ipc.broadcast(
                {"type": "state", "listening": self.listening, "status": status}
            )

        while not self._shutdown.is_set():
            chunk = await mic.read()
            ring.append(chunk)
            block += 1
            if block % 5 == 0:
                await self._emit_level(chunk)

            if not self.listening:
                continue

            if state == "wake-listening":
                detections = self._wake.process(chunk) if self._wake else []
                if detections:
                    state = "capturing"
                    detector.arm()
                    pre_trigger = ring.get_last(pad_samples)
                    det = detections[0]
                    await self._ipc.broadcast({"type": "wake", **det.to_dict()})
                    await set_status("capturing")
                    if cfg.play_chime:
                        await asyncio.to_thread(self._speaker.play_chime)
            elif state == "capturing":
                utterance = detector.feed(chunk)
                if utterance is not None:
                    state = "wake-listening"
                    await set_status("processing")
                    audio = np.concatenate([pre_trigger, utterance])
                    await self._process_utterance(audio)

    async def _emit_level(self, chunk: np.ndarray) -> None:
        now = time.monotonic()
        if now - self._level_last < 0.04:
            return
        self._level_last = now
        level = float(np.sqrt(np.mean(np.square(chunk))))
        await self._ipc.broadcast({"type": "levels", "rms": round(level, 4)})

    async def _process_utterance(self, audio: np.ndarray) -> None:
        if self._stt is None:
            return
        try:
            text = await asyncio.to_thread(self._stt.transcribe, audio, self.config.stt.language)
        except Exception as exc:  # noqa: BLE001
            logger.warning("transcription failed: %s", exc)
            text = ""
        await self._ipc.broadcast(
            {"type": "transcript", "text": text, "final": True, "source": "voice"}
        )
        if text and self.config.demo_echo and self._tts is not None:
            await asyncio.to_thread(self._tts.speak, text)
        await self._ipc.broadcast({"type": "state", "listening": self.listening, "status": "ready"})

    # -------------------------------------------------------------------- commands

    async def _handle_message(self, message: dict) -> dict | None:
        kind = message.get("type")
        if kind == "ping":
            return {"type": "pong", "ok": True}
        if kind == "set_listening":
            self.listening = bool(message.get("value", True))
            await self._ipc.broadcast(
                {"type": "state", "listening": self.listening, "status": "ready"}
            )
            return {"type": "ack", "ok": True}
        if kind == "get_state":
            return {
                "type": "state",
                "ok": True,
                "listening": self.listening,
                "status": "ready",
            }
        return {"type": "error", "ok": False, "error": f"unknown command {kind!r}"}
