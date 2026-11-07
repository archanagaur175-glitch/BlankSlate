# daemon/jarvis — vendored fork of isair/jarvis

This directory contains a **vendored copy** of the `src/jarvis` package from
[isair/jarvis](https://github.com/isair/jarvis), used as the agentic core of
the BlankSlate daemon.

## License

The code here is governed by the **Jarvis AI Assistant License** (a
non-commercial license). The original `LICENSE` file is retained verbatim in
this directory and MUST stay present in any distribution. In short:

- Personal, educational, and research use is permitted free of charge.
- You may not sell, rent, lease, or otherwise commercialise the software.
- Any derivative work must be released under the same non-commercial terms.
- Commercial use requires a separate license from the upstream author
  (baris@writeme.com).

Because this component is non-commercial, BlankSlate as a whole is distributed
for **non-commercial, personal use**.

## What we kept (from upstream)

- Wake-word-anywhere intent judging (`listening/intent_judge.py`,
  `listening/wake_detection.py`)
- Audio capture / push-to-talk pipeline and state machine
  (`listening/listener.py`, `listening/state_manager.py`)
- Local STT integration (`dictation/`)
- Tool router and MCP client logic (`tools/`)
- Ollama LLM backend (`llm/ollama.py`)
- Reply orchestration (`reply/engine.py`)

## What we changed

- **Branding**: user-facing "Jarvis" strings replaced with "BlankSlate"
  (reply label, default wake word, entry-point docstrings). Internal Python
  import paths (`jarvis.*`) are intentionally left unchanged to avoid breaking
  the module graph.
- **`num_ctx` is now config-driven** (`ollama_num_ctx` in settings, default
  8192) instead of hardcoded in `llm/ollama.py`, so it can be lowered on
  VRAM-constrained GPUs without a code change.
- The upstream `desktop_app/` GUI is **not** vendored — it is replaced by the
  BlankSlate Tauri HUD (`hud/`). The `from desktop_app.face_widget import ...`
  calls inside `listening/` and `output/tts.py` are lazy (function-local) and
  will be rewired to the HUD's IPC in the HUD integration commit.

Upstream's README at fork time is preserved in `README.upstream.md`.
