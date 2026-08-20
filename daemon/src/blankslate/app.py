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
        self._tts: TTSEngine | None = None
        self._pipeline_task: asyncio.Task | None = None
        self._level_last: float = 0.0
        self._agent: Agent | None = None
        self._history: HistoryStore | None = None
        self._digest: Digester | None = None
        self._mcp: McpRunner | None = None
        self._judge: IntentJudge | None = None
        self._agent_available = False

    # ------------------------------------------------------------------ lifecycle

    async def run(self) -> None:
        self.config.ensure_dirs()
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
        if text:
            await self._route_text(text, source="voice")
        await self._ipc.broadcast({"type": "state", "listening": self.listening, "status": "ready"})

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
