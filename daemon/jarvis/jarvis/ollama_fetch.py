"""First-run fetch of the Ollama models the daemon requires.

On startup the daemon ensures the chat/embedding/fast models configured in
``cfg`` are present in the local Ollama instance, pulling any that are missing
and streaming progress to the HUD via ``ollama_fetch`` IPC events
(``{"type": "ollama_fetch", "stage", "percent", "eta"}``).

This is the vendored replacement for the old standalone ``ollama_fetch`` step:
instead of the desktop app pushing progress over stdout, the daemon itself owns
the pull and reports over the same WebSocket the HUD already listens to.
"""

from __future__ import annotations

import json
import time

import requests

from .debug import debug_log
from .ipc import broadcast_ollama_fetch


def _list_models(base_url: str):
    """Return the set of model names present in Ollama, or None if unreachable."""
    try:
        r = requests.get(base_url.rstrip("/") + "/api/tags", timeout=10)
        r.raise_for_status()
        data = r.json()
        return {m.get("name", "") for m in data.get("models", [])}
    except Exception as e:
        debug_log(f"ollama_fetch: could not list models: {e}", "ollama_fetch")
        return None


def _pull_model(base_url: str, name: str, model_index: int, model_total: int) -> None:
    """Pull a single model, streaming progress as cumulative ollama_fetch events."""
    url = base_url.rstrip("/") + "/api/pull"
    start = time.time()
    last_emit = 0.0
    last_abs = -1

    def _emit(stage: str, abs_percent: int, eta: int, force: bool = False) -> None:
        nonlocal last_emit, last_abs
        now = time.time()
        if force or (abs_percent != last_abs and now - last_emit >= 0.25):
            last_abs = abs_percent
            last_emit = now
            broadcast_ollama_fetch(stage, abs_percent, eta)

    try:
        with requests.post(
            url, json={"model": name, "stream": True}, stream=True, timeout=1800
        ) as r:
            r.raise_for_status()
            for line in r.iter_lines(decode_unicode=True):
                if not line:
                    continue
                try:
                    obj = json.loads(line)
                except Exception:
                    continue
                status = obj.get("status", "")
                total = obj.get("total")
                completed = obj.get("completed")
                if total and completed is not None and total > 0:
                    frac = completed / total
                    abs_percent = int((model_index + frac) / model_total * 100)
                    eta = 0
                    if completed > 0:
                        elapsed = time.time() - start
                        rate = completed / elapsed if elapsed > 0 else 0
                        if rate > 0:
                            eta = int((total - completed) / rate)
                    _emit(f"pulling {name} — {status}", abs_percent, eta)
                else:
                    abs_percent = int(model_index / model_total * 100)
                    _emit(f"pulling {name} — {status}", abs_percent, 0)
                if status == "success":
                    break
    except Exception as e:
        debug_log(f"ollama_fetch: pull of {name} failed: {e}", "ollama_fetch")
        broadcast_ollama_fetch(
            f"error pulling {name}: {e}", int(model_index / model_total * 100), 0
        )
        raise

    broadcast_ollama_fetch(
        f"pulled {name}", int((model_index + 1) / model_total * 100), 0
    )


def ensure_models(cfg, sink=None, models=None) -> None:
    """Ensure the required Ollama models are present, pulling any that are missing.

    Emits ``ollama_fetch`` events for each model and a final ``models ready``
    event at 100%. Failures are reported as error-stage events and do not abort
    the daemon.
    """
    base = getattr(cfg, "ollama_base_url", "http://127.0.0.1:11434")

    if models is None:
        models = []
        for m in (
            getattr(cfg, "ollama_chat_model", ""),
            getattr(cfg, "ollama_embed_model", ""),
        ):
            if m and m not in models:
                models.append(m)
        fast = getattr(cfg, "fast_model", "")
        if fast and fast not in models:
            models.append(fast)
    models = [m for m in models if m]

    if not models:
        broadcast_ollama_fetch("models ready", 100, 0)
        return

    present = _list_models(base)
    if present is None:
        broadcast_ollama_fetch("Ollama unavailable — cannot fetch models", 0, 0)
        return

    # Ollama reports tags with an explicit ":latest" suffix; the config usually
    # omits it. Treat "name" and "name:latest" as the same model so we don't
    # re-pull an already-present model on every startup.
    present_norm = {p[:-len(":latest")] if p.endswith(":latest") else p for p in present}

    missing = [m for m in models if m not in present_norm]
    if not missing:
        debug_log("ollama_fetch: all required models present", "ollama_fetch")
        broadcast_ollama_fetch("models ready", 100, 0)
        return

    debug_log(f"ollama_fetch: pulling {missing}", "ollama_fetch")
    total = len(missing)
    for i, name in enumerate(missing):
        broadcast_ollama_fetch(f"pulling {name}", int(i / total * 100), 0)
        try:
            _pull_model(base, name, i, total)
        except Exception:
            # Error already emitted; continue with remaining models.
            pass

    broadcast_ollama_fetch("models ready", 100, 0)
