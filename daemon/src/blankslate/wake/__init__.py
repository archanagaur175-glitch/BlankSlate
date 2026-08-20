"""Wake engine factory."""

from __future__ import annotations

from .openwakeword_engine import OpenWakeWordEngine, WakeEngine


def build_wake_engine(
    engine: str,
    model: str,
    threshold: float,
    trigger_level: int,
) -> WakeEngine:
    if engine == "openwakeword":
        return OpenWakeWordEngine(model=model, threshold=threshold, trigger_level=trigger_level)
    raise ValueError(f"unknown wake engine: {engine}")
