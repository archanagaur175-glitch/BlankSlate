from pathlib import Path

from blankslate.config import (
    DaemonConfig,
    default_data_dir,
)

SAMPLE = {
    "log_level": "DEBUG",
    "demo_echo": True,
    "audio": {"vad_mode": 3, "ring_seconds": 5.0},
    "wake": {"model": "alexa", "threshold": 0.42},
    "stt": {"model": "small.en"},
    "tts": {"voice": "am_michael"},
    "llm": {"model": "qwen3:8b"},
    "search": {"backends": ["duckduckgo"]},
    "unknown_key": "ignored",
}


def test_defaults() -> None:
    cfg = DaemonConfig()
    assert cfg.wake.model == "hey_jarvis"
    assert cfg.stt.model == "base.en"
    assert cfg.ipc.host == "127.0.0.1"


def test_from_dict_round_trip() -> None:
    cfg = DaemonConfig.from_dict(SAMPLE)
    assert cfg.log_level == "DEBUG"
    assert cfg.audio.vad_mode == 3
    assert cfg.audio.ring_seconds == 5.0
    assert cfg.wake.threshold == 0.42
    assert cfg.stt.model == "small.en"
    assert cfg.tts.voice == "am_michael"
    assert cfg.llm.model == "qwen3:8b"
    assert cfg.search.backends == ["duckduckgo"]
    assert "unknown_key" not in cfg.to_dict()


def test_save_load(tmp_path) -> None:
    cfg = DaemonConfig.from_dict(SAMPLE)
    path = tmp_path / "config.json"
    cfg.save(path)
    loaded = DaemonConfig.load(path)
    assert loaded.audio.vad_mode == 3
    assert loaded.wake.threshold == 0.42
    assert loaded.tts.voice == "am_michael"


def test_load_missing_file(tmp_path) -> None:
    loaded = DaemonConfig.load(tmp_path / "nope.json")
    assert loaded == DaemonConfig()


def test_data_dir_default(monkeypatch) -> None:
    monkeypatch.setenv("LOCALAPPDATA", "C:/nondir/AppData/Local")
    assert default_data_dir() == Path("C:/nondir/AppData/Local/BlankSlate")


def test_paths_resolution(tmp_path) -> None:
    cfg = DaemonConfig(data_dir=str(tmp_path), models_dir=str(tmp_path / "m"))
    assert cfg.resolved_data_dir() == tmp_path
    assert cfg.resolved_models_dir() == tmp_path / "m"
    assert cfg.db_path().name == "history.sqlite3"
    cfg.ensure_dirs()
    assert (tmp_path / "m").is_dir()


def test_invalid_json_returns_defaults(tmp_path) -> None:
    p = tmp_path / "config.json"
    p.write_text("not json", encoding="utf-8")
    cfg = DaemonConfig.load(p)
    assert cfg == DaemonConfig()
