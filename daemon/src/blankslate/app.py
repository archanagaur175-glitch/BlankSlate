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

from blankslate.agent import Agent, AgentOptions
from blankslate.audio.io import MicCapture, MicCaptureError, Speaker
from blankslate.audio.ringbuffer import RingBuffer
from blankslate.audio.vad import UtteranceDetector, Vad
from blankslate.config import DaemonConfig
from blankslate.input.hotkey import HotkeyManager
from blankslate.ipc.server import IpcServer
from blankslate.llm.ollama import OllamaProvider
from blankslate.mcp.mcp_runner import McpRunner
from blankslate.memory import HistoryStore
from blankslate.memory.digest import Digester
from blankslate.nlu.intent import IntentJudge
from blankslate.nlu.planner import TaskPlanner
from blankslate.router.embeddings import Embedder
from blankslate.router.tool_router import ToolRouter
from blankslate.security.redactor import Redactor
from blankslate.stt.engine import STTEngine, build_stt_engine
from blankslate.tools.native import NativeToolRunner
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
        self._dict_stt: STTEngine | None = None
        self._tts: TTSEngine | None = None
        self._pipeline_task: asyncio.Task | None = None
        self._level_last: float = 0.0
        self._agent: Agent | None = None
        self._history: HistoryStore | None = None
        self._digest: Digester | None = None
        self._mcp: McpRunner | None = None
        self._judge: IntentJudge | None = None
        self._agent_available = False
        self._loop: asyncio.AbstractEventLoop | None = None
        self._wake_enabled: bool = config.wake.enabled
        self._ptt_active: bool = False
        self._ptt_request: str | None = None
        self._ptt_detector: UtteranceDetector | None = None
        self._hotkey_mgr: HotkeyManager | None = None
        self._state: str = "idle"

    # ------------------------------------------------------------------ lifecycle

    async def run(self) -> None:
        self.config.ensure_dirs()
        self._loop = asyncio.get_running_loop()
        self._build_agent_stack()
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
        if self._hotkey_mgr is not None:
            self._hotkey_mgr.stop()
        if self._capture is not None:
            self._capture.stop()
        if self._pipeline_task is not None:
            self._pipeline_task.cancel()
            try:
                await self._pipeline_task
            except asyncio.CancelledError:
                pass
        await self._ipc.stop()

    def _build_agent_stack(self) -> None:
        cfg = self.config
        data_dir = cfg.resolved_data_dir()
        llm: OllamaProvider | None = None
        try:
            llm = OllamaProvider(
                base_url=cfg.llm.base_url,
                model=cfg.llm.model,
                timeout_s=cfg.llm.timeout_s,
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("LLM unavailable: %s", exc)

        mcp: McpRunner | None = None
        if cfg.mcp.servers:
            try:
                mcp = McpRunner.from_config_dicts(cfg.mcp.servers)
            except Exception as exc:  # noqa: BLE001
                logger.warning("MCP init failed: %s", exc)

        embedder = Embedder(
            provider=cfg.tool_router.embeddings_provider,
            model=cfg.tool_router.embedding_model,
            base_url=cfg.llm.base_url,
        )
        router = ToolRouter(
            strategy=cfg.tool_router.strategy,
            embedder=embedder,
            llm=llm,
            top_k=cfg.tool_router.top_k,
        )
        redactor = Redactor(
            enabled=cfg.redaction.enabled, extra_patterns=cfg.redaction.extra_patterns
        )
        native = NativeToolRunner(data_dir)
        history = HistoryStore(cfg.db_path(), redactor)
        judge = IntentJudge(llm=None, wake_words=[cfg.wake.model])
        planner = TaskPlanner(llm)
        self._mcp = mcp
        self._agent = Agent(
            llm=llm,
            router=router,
            native=native,
            planner=planner,
            options=AgentOptions(
                system_prompt=cfg.agents.system_prompt,
                max_iterations=cfg.agents.max_iterations,
                temperature=cfg.agents.temperature,
            ),
            event_cb=self._agent_event,
            mcp_lister=mcp.list_tools if mcp else None,
            mcp_caller=self._mcp_call if mcp else None,
            mcp_server_names=mcp.list_servers() if mcp else [],
        )
        self._judge = judge
        self._agent_available = llm is not None and cfg.agents.enabled
        self._history = history
        self._digest = Digester(llm, max_chars=cfg.context.max_tool_output_chars)

    async def _agent_event(self, event: str, payload: dict) -> None:
        await self._ipc.broadcast({"type": f"agent.{event}", **payload})

    async def _mcp_call(self, server: str, tool: str, arguments: dict) -> str:
        if self._mcp is None:
            return "MCP unavailable."
        try:
            texts = await self._mcp.call(server, tool, arguments)
            return "\n".join(texts) or "OK"
        except Exception as exc:  # noqa: BLE001
            logger.warning("mcp call failed (%s/%s): %s", server, tool, exc)
            return f"MCP error: {exc}"

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
            self._dict_stt = build_stt_engine(
                cfg.stt.engine, cfg.dictation.model, cfg.stt.device, cfg.stt.compute
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("dictation STT unavailable: %s", exc)
            self._dict_stt = self._stt
        try:
            self._wake = build_wake_engine(
                cfg.wake.engine, cfg.wake.model, cfg.wake.threshold, cfg.wake.trigger_level
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("wake engine unavailable: %s", exc)
            self._wake = None
        self._tts = build_tts_engine(cfg.tts.engine, self._speaker, cfg.tts.voice, cfg.tts.speed)
        self._wake_enabled = cfg.wake.enabled and self._wake is not None

        dict_cfg = cfg.dictation
        self._hotkey_mgr = HotkeyManager(
            dict_cfg.hotkey,
            on_start=self._ptt_press,
            on_stop=self._ptt_release,
            hold_to_talk=dict_cfg.hold_to_talk,
        )
        try:
            self._hotkey_mgr.start()
        except Exception as exc:  # noqa: BLE001
            logger.warning("push-to-talk hotkey disabled: %s", exc)
            self._hotkey_mgr = None

        if self._stt is not None:
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
        wake_detector = UtteranceDetector(
            cfg.sample_rate, vad, cfg.end_silence_ms, cfg.max_utterance_ms, cfg.block_ms
        )
        pad_samples = int(cfg.sample_rate * cfg.pre_trigger_pad_ms / 1000)
        pre_trigger: np.ndarray = np.zeros(0, dtype=np.float32)
        self._state = "wake-listening" if self._wake_enabled else "idle"
        block = 0

        while not self._shutdown.is_set():
            chunk = await mic.read()
            ring.append(chunk)
            block += 1
            if block % 5 == 0:
                await self._emit_level(chunk)

            # Push-to-talk requests are honoured regardless of the wake toggle so
            # the HUD / hotkey can always capture a dictation turn.
            req = self._ptt_request
            if req is not None:
                self._ptt_request = None
                if req == "start" and self._state not in ("capturing", "ptt"):
                    self._state = "ptt"
                    self._ptt_active = True
                    self._ptt_detector = UtteranceDetector(
                        cfg.sample_rate,
                        vad,
                        self.config.dictation.max_utterance_ms,
                        self.config.dictation.max_utterance_ms,
                        cfg.block_ms,
                    )
                    self._ptt_detector.arm()
                    await self._broadcast_state("capturing")
                    if cfg.play_chime:
                        await asyncio.to_thread(self._speaker.play_chime)
                elif req == "stop" and self._state == "ptt":
                    audio = self._ptt_detector.finalize() if self._ptt_detector else None
                    self._ptt_active = False
                    self._ptt_detector = None
                    self._state = "wake-listening" if self._wake_enabled else "idle"
                    await self._broadcast_state("processing")
                    if audio is not None and audio.size:
                        await self._process_utterance(audio, source="dictation")

            if self._state == "wake-listening" and self.listening:
                detections = self._wake.process(chunk) if self._wake else []
                if detections:
                    self._state = "capturing"
                    wake_detector.arm()
                    pre_trigger = ring.get_last(pad_samples)
                    det = detections[0]
                    await self._ipc.broadcast({"type": "wake", **det.to_dict()})
                    await self._broadcast_state("capturing")
                    if cfg.play_chime:
                        await asyncio.to_thread(self._speaker.play_chime)
            elif self._state in ("capturing", "ptt"):
                detector = wake_detector if self._state == "capturing" else self._ptt_detector
                if detector is None:
                    self._state = "wake-listening" if self._wake_enabled else "idle"
                    continue
                utterance = detector.feed(chunk)
                if utterance is not None:
                    if self._state == "capturing":
                        self._state = "wake-listening"
                        await self._broadcast_state("processing")
                        audio = np.concatenate([pre_trigger, utterance])
                        await self._process_utterance(audio)
                    else:
                        self._ptt_active = False
                        self._ptt_detector = None
                        self._state = "wake-listening" if self._wake_enabled else "idle"
                        await self._broadcast_state("processing")
                        await self._process_utterance(utterance, source="dictation")

    async def _emit_level(self, chunk: np.ndarray) -> None:
        now = time.monotonic()
        if now - self._level_last < 0.04:
            return
        self._level_last = now
        level = float(np.sqrt(np.mean(np.square(chunk))))
        await self._ipc.broadcast({"type": "levels", "rms": round(level, 4)})

    async def _broadcast_state(self, status: str) -> None:
        await self._ipc.broadcast(
            {
                "type": "state",
                "listening": self.listening,
                "status": status,
                "wake_enabled": self._wake_enabled,
                "ptt_active": self._ptt_active,
            }
        )

    async def _process_utterance(self, audio: np.ndarray, source: str = "voice") -> None:
        if source == "dictation":
            engine = self._dict_stt or self._stt
            lang = self.config.dictation.language
        else:
            engine = self._stt
            lang = self.config.stt.language
        if engine is None:
            return
        try:
            text = await asyncio.to_thread(engine.transcribe, audio, lang)
        except Exception as exc:  # noqa: BLE001
            logger.warning("transcription failed: %s", exc)
            text = ""
        await self._ipc.broadcast(
            {"type": "transcript", "text": text, "final": True, "source": source}
        )
        if text:
            await self._route_text(text, source=source)
        await self._broadcast_state("ready")

    # ------------------------------------------------------- push-to-talk input

    def _ptt_press(self) -> None:
        if self._loop is None:
            return
        self._loop.call_soon_threadsafe(self._request_ptt, "start")

    def _ptt_release(self) -> None:
        if self._loop is None:
            return
        self._loop.call_soon_threadsafe(self._request_ptt, "stop")

    def _request_ptt(self, action: str) -> None:
        self._ptt_request = action

    def _set_wake(self, enabled: bool) -> None:
        self._wake_enabled = bool(enabled) and self._wake is not None
        if self._wake_enabled and self._state == "idle":
            self._state = "wake-listening"

    async def _route_text(self, text: str, source: str = "voice") -> None:
        if not self._agent_available or self._agent is None or self._judge is None:
            if text and self.config.demo_echo and self._tts is not None:
                await asyncio.to_thread(self._tts.speak, text)
            return

        intent = await self._judge.judge(text)
        await self._ipc.broadcast({"type": "intent", **intent.to_dict(), "source_input": source})
        if not intent.directed:
            return

        history_turns = []
        if self._history is not None:
            history_turns = [
                {"role": row["role"], "content": row["content"]}
                for row in self._history.recent(self.config.context.history_turns)
                if row["role"] in ("user", "assistant")
            ]

        reply = await self._agent.handle(intent.query, history_turns)
        if self._history is not None:
            self._history.append("user", intent.query, source=source)
            self._history.append("assistant", reply or "")
        if self._digest is not None and self.config.context.digest_on:
            summary = await self._digest.digest(f"User: {text}\nAssistant: {reply or ''}")
            await self._ipc.broadcast({"type": "recall_digest", "summary": summary})
        if reply and self._tts is not None:
            await asyncio.to_thread(self._tts.speak, reply)

    # -------------------------------------------------------------------- commands

    async def _handle_message(self, message: dict) -> dict | None:
        kind = message.get("type")
        if kind == "ping":
            return {"type": "pong", "ok": True}
        if kind == "set_listening":
            self.listening = bool(message.get("value", True))
            await self._broadcast_state("ready")
            return {"type": "ack", "ok": True}
        if kind == "start_dictation":
            self._ptt_request = "start"
            return {"type": "ack", "ok": True}
        if kind == "stop_dictation":
            self._ptt_request = "stop"
            return {"type": "ack", "ok": True}
        if kind == "set_wake":
            self._set_wake(bool(message.get("value", False)))
            await self._broadcast_state(
                "capturing" if self._state in ("capturing", "ptt") else "ready"
            )
            return {"type": "ack", "ok": True}
        if kind == "get_state":
            return {
                "type": "state",
                "ok": True,
                "listening": self.listening,
                "status": "ready",
                "wake_enabled": self._wake_enabled,
                "ptt_active": self._ptt_active,
            }
        return {"type": "error", "ok": False, "error": f"unknown command {kind!r}"}
