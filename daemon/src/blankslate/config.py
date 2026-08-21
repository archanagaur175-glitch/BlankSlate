"""Configuration model for the BlankSlate daemon.

Config is a plain JSON document stored in the user's data directory. All
fields are dataclasses with defaults so the daemon runs with zero config.
"""

from __future__ import annotations

import dataclasses
import json
import os
from dataclasses import dataclass, field, is_dataclass
from pathlib import Path
from typing import get_type_hints


def default_data_dir() -> Path:
    base = os.environ.get("LOCALAPPDATA") or str(Path.home() / "AppData" / "Local")
    return Path(base) / "BlankSlate"


@dataclass
class _Settings:
    def to_dict(self) -> dict:
        return dataclasses.asdict(self)

    @classmethod
    def from_dict(cls, raw: dict) -> _Settings:
        fields = {f.name: f for f in dataclasses.fields(cls)}
        hints = get_type_hints(cls)
        kwargs = {}
        for key, value in raw.items():
            if key not in fields:
                continue
            hint = hints.get(key)
            if is_dataclass(hint) and isinstance(value, dict):
                kwargs[key] = hint.from_dict(value)
            else:
                kwargs[key] = value
        return cls(**kwargs)


@dataclass
class AudioConfig(_Settings):
    sample_rate: int = 16000
    channels: int = 1
    block_ms: int = 30
    ring_seconds: float = 8.0
    vad_mode: int = 2
    pre_trigger_pad_ms: int = 1500
    end_silence_ms: int = 700
    max_utterance_ms: int = 20000
    play_chime: bool = True


@dataclass
class WakeConfig(_Settings):
    engine: str = "openwakeword"
    model: str = "hey_jarvis"
    threshold: float = 0.6
    trigger_level: int = 1
    switch_delay_ms: int = 1500
    enabled: bool = True


@dataclass
class SttConfig(_Settings):
    engine: str = "faster-whisper"
    model: str = "base.en"
    device: str = "auto"
    compute: str = "int8"
    language: str | None = None


@dataclass
class TtsConfig(_Settings):
    engine: str = "kokoro"
    voice: str = "af_heart"
    speed: float = 1.0


@dataclass
class LlmConfig(_Settings):
    provider: str = "ollama"
    base_url: str = "http://127.0.0.1:11434"
    model: str = "qwen3:4b"
    api_key: str = ""
    timeout_s: float = 60.0


@dataclass
class IpcConfig(_Settings):
    host: str = "127.0.0.1"
    port: int = 0


@dataclass
class ContextConfig(_Settings):
    history_turns: int = 8
    digest_on: bool = True
    max_tool_output_chars: int = 4000


@dataclass
class AgentsConfig(_Settings):
    enabled: bool = True
    max_iterations: int = 6
    temperature: float = 0.3
    system_prompt: str = (
        "You are BlankSlate, a private, local-first voice assistant. Be concise "
        "and accurate. Use tools when they help, and clearly report what you did."
    )


@dataclass
class McpConfig(_Settings):
    servers: list[dict] = field(default_factory=list)


@dataclass
class ToolRouterConfig(_Settings):
    strategy: str = "embedding"
    top_k: int = 10
    embedding_model: str = "nomic-embed-text"
    embeddings_provider: str = "ollama"


@dataclass
class DictationConfig(_Settings):
    hotkey: str = "<ctrl>+<alt>+d"
    hold_to_talk: bool = True
    model: str = "small.en"
    language: str | None = None
    end_silence_ms: int = 700
    max_utterance_ms: int = 120000


@dataclass
class SearchConfig(_Settings):
    enabled: bool = True
    backends: list[str] = field(
        default_factory=lambda: ["duckduckgo", "bing", "brave", "wikipedia"]
    )
    max_results: int = 5


@dataclass
class RedactionConfig(_Settings):
    enabled: bool = True
    extra_patterns: list[str] = field(default_factory=list)


@dataclass
class DaemonConfig(_Settings):
    data_dir: str = ""
    models_dir: str = ""
    log_level: str = "INFO"
    demo_echo: bool = False
    audio: AudioConfig = field(default_factory=AudioConfig)
    wake: WakeConfig = field(default_factory=WakeConfig)
    stt: SttConfig = field(default_factory=SttConfig)
    tts: TtsConfig = field(default_factory=TtsConfig)
    llm: LlmConfig = field(default_factory=LlmConfig)
    ipc: IpcConfig = field(default_factory=IpcConfig)
    context: ContextConfig = field(default_factory=ContextConfig)
    agents: AgentsConfig = field(default_factory=AgentsConfig)
    mcp: McpConfig = field(default_factory=McpConfig)
    tool_router: ToolRouterConfig = field(default_factory=ToolRouterConfig)
    dictation: DictationConfig = field(default_factory=DictationConfig)
    search: SearchConfig = field(default_factory=SearchConfig)
    redaction: RedactionConfig = field(default_factory=RedactionConfig)

    # ------------------------------------------------------------------ paths

    def resolved_data_dir(self) -> Path:
        if self.data_dir:
            return Path(self.data_dir).expanduser()
        return default_data_dir()

    def resolved_models_dir(self) -> Path:
        if self.models_dir:
            return Path(self.models_dir).expanduser()
        return self.resolved_data_dir() / "models"

    def config_path(self) -> Path:
        return self.resolved_data_dir() / "config.json"

    def ipc_path(self) -> Path:
        return self.resolved_data_dir() / "ipc.json"

    def db_path(self) -> Path:
        return self.resolved_data_dir() / "history.sqlite3"

    def ensure_dirs(self) -> None:
        for path in (self.resolved_data_dir(), self.resolved_models_dir()):
            path.mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------ persistence

    @classmethod
    def load(cls, path: str | Path | None = None) -> DaemonConfig:
        if path:
            p = Path(path)
        else:
            p = default_data_dir() / "config.json"
        if not p.exists():
            return cls()
        try:
            raw = json.loads(p.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return cls()
        return cls.from_dict(raw)

    def save(self, path: str | Path | None = None) -> Path:
        target = Path(path) if path else self.config_path()
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(self.to_dict(), indent=2, sort_keys=True), encoding="utf-8")
        return target
