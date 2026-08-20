# BlankSlate

**100% free, open-source, local-first AI voice assistant for Windows 11.**

BlankSlate is a wake-word-driven voice assistant that runs entirely on your machine.
No subscriptions, no forced cloud calls, no query caps. It listens for a wake word,
understands what you say with a local LLM (via [Ollama](https://ollama.com)),
acts on your Windows desktop through native tools and MCP servers, and responds
with a local neural voice — all while a polished, audio-reactive Fluent-style HUD
floats above your desktop.

## Highlights

- **Wake word anywhere in the sentence** — say *"BlankSlate, what do you think
  about that?"* and it resolves against recent conversation without repeating the
  wake word.
- **Deep Windows 11 automation** — launch/focus/close/snap apps, switch virtual
  desktops, control volume/brightness, lock, screenshot, browse files, and search
  the web (local-first, gracefully degrading on failure).
- **Offline dictation** — hold a global hotkey, speak, release, and the transcript
  is pasted into whatever app has focus.
- **Embedding-based smart tool selection** — add unlimited tools/MCP servers;
  latency and accuracy never degrade ("zero context rot").
- **Secret/PII auto-redaction** — nothing sensitive is ever written to disk.
- **Gorgeous Fluent dark HUD** with real Windows Mica/acrylic, reactive waveform,
  and an instant light-mode toggle — original design, no reskinned branding.

## Architecture

```
┌─────────────────────────────┐   loopback WebSocket    ┌──────────────────────┐
│  Daemon (Python 3.11)        │  (token-authenticated) │  HUD (Tauri v2)       │
│  mic → VAD → wake word →     │◄──────────────────────►│  Mica/acrylic HUD      │
│  STT → intent judge → LLM →  │                        │  live waveform +       │
│  tool router → native/MCP    │                        │  transcript + tray     │
│  tools → TTS                  │                        │  dictation history     │
└─────────────────────────────┘                        └──────────────────────┘
```

- **Daemon** (`daemon/`, Python 3.11, asyncio): owns the microphone, wake-word
  detection (openwakeword), local Whisper transcription (faster-whisper), the
  agentic loop against a local Ollama model, Piper-free neural TTS (Kokoro with a
  Windows-native fallback), the global-hotkey dictation pipeline, and the tool/MCP
  runtime. Lives in the system tray, can auto-start with Windows.
- **HUD** (`hud/`, Tauri v2 + Rust + Svelte): the floating Fluent interface —
  listening state, live transcript, audio-reactive waveform, active tool calls,
  compact conversation history, and the tray manager.

## Quick start (from source)

1. Install [Ollama](https://ollama.com) and pull the default model:
   `ollama pull qwen3:4b`
2. Install Python 3.11 and set up the daemon:
   ```powershell
   cd daemon
   python -m venv .venv
   .\.venv\Scripts\Activate.ps1
   pip install -e ".[dev]"
   blankslate --config ..\blankslate-data\config.json
   ```
3. Build and run the HUD:
   ```powershell
   cd ..\hud
   pnpm install
   pnpm tauri dev
   ```

See `docs/` for architecture, MCP configuration, wake-word training, and the
manual QA checklist.

## Licensing

BlankSlate is licensed under the **Apache License 2.0** (see `LICENSE`).

Every third-party dependency and bundled asset is audited for license
compatibility; see `THIRD_PARTY_NOTICES.md` and `scripts/license_audit.py`.
Copyleft (GPL/AGPL) code is never imported or linked — GPL programs such as
espeak-ng are only ever invoked as separate, clearly-labeled subprocesses.

The commercial competitor Jarvis.app and the isair/jarvis project are used
strictly as design references; no code from either is copied into BlankSlate.
