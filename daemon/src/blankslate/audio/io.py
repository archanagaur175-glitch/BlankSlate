"""Microphone capture and audio playback.

Both modules wrap sounddevice (PortAudio) and are safe to import on machines
without audio hardware; construction failures surface as handled errors so the
rest of the daemon keeps running.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable

import numpy as np

logger = logging.getLogger(__name__)

ChunkConsumer = Callable[[np.ndarray], Awaitable[None]]


class MicCaptureError(RuntimeError):
    pass


class MicCapture:
    """Streams mono float32 blocks at ``sample_rate`` onto an asyncio queue.

    The PortAudio callback thread uses ``call_soon_threadsafe`` to hand blocks
    to the event loop, so the daemon can process audio without blocking.
    """

    def __init__(
        self,
        sample_rate: int = 16000,
        channels: int = 1,
        block_ms: int = 30,
        device: int | None = None,
    ) -> None:
        self.sample_rate = sample_rate
        self.channels = channels
        self.block_ms = block_ms
        self.device = device
        self._input: object | None = None
        self._queue: asyncio.Queue[np.ndarray] | None = None
        self._loop: asyncio.AbstractEventLoop | None = None

    def start(self) -> None:
        import sounddevice as sd

        if not self._loop:
            self._loop = asyncio.get_running_loop()
            self._queue = asyncio.Queue(maxsize=200)

        frames = int(self.sample_rate * self.block_ms / 1000)

        def callback(indata, frames_out, time_info, status) -> None:  # noqa: ANN001
            if status:
                logger.debug("mic status: %s", status)
            chunk = np.asarray(indata, dtype=np.float32).reshape(-1)
            if self._loop and not self._loop.is_closed():
                self._loop.call_soon_threadsafe(self._queue.put_nowait, chunk.copy())

        try:
            self._input = sd.InputStream(
                samplerate=self.sample_rate,
                channels=self.channels,
                callback=callback,
                blocksize=frames,
                device=self.device,
                dtype="float32",
            )
            self._input.start()
        except Exception as exc:  # noqa: BLE001
            raise MicCaptureError(f"could not open microphone: {exc}") from exc

    async def read(self) -> np.ndarray:
        if self._queue is None:
            raise MicCaptureError("MicCapture not started")
        return await self._queue.get()

    def stop(self) -> None:
        if self._input is not None:
            try:
                self._input.stop()
                self._input.close()
            except Exception:  # noqa: BLE001
                pass
        self._input = None


class Speaker:
    """Non-blocking playback of mono float32 audio for any sample rate."""

    def __init__(self, device: int | None = None) -> None:
        self.device = device

    def _play_sync(self, audio: np.ndarray, sample_rate: int) -> None:
        import sounddevice as sd

        sample = np.asarray(audio, dtype=np.float32).reshape(-1)
        if sample.size == 0:
            return
        sd.play(sample, samplerate=sample_rate, device=self.device, blocking=True)

    def play(self, audio: np.ndarray, sample_rate: int) -> None:
        """Synchronous play; call from a worker thread when inside asyncio."""
        try:
            self._play_sync(audio, sample_rate)
        except Exception as exc:  # noqa: BLE001
            logger.warning("playback failed: %s", exc)

    def play_chime(self, sample_rate: int = 16000, duration_ms: int = 120) -> None:
        """A short attention tone used as instant audio feedback."""
        n = int(sample_rate * duration_ms / 1000)
        t = np.linspace(0, duration_ms / 1000, n, endpoint=False)
        wave = 0.25 * np.sin(2 * np.pi * 880.0 * t) * np.exp(-6.0 * t)
        self.play(wave, sample_rate)
