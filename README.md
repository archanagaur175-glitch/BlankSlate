# BlankSlate

**A free, open-source, local-first AI voice assistant for Windows 11.**

BlankSlate is a wake-word-driven voice assistant that runs on your machine. It
listens for a wake word, transcribes speech locally, runs an agentic loop against a
local Ollama model, acts on the Windows desktop through native tools and MCP
servers, and answers with a local neural voice — while a Fluent-style HUD floats
above the desktop.

## Highlights

- **Wake-word driven** — the daemon owns the microphone, voice activity detection
  and wake-word detection, and resolves a wake word against recent conversation.
- **Local speech pipeline** — local Whisper transcription and neural TTS, with the
  LLM delegated to a local Ollama instance.
- **Windows automation** — native tools plus an MCP runtime act on the desktop.
- **Offline dictation** — a global-hotkey dictation pipeline pastes the transcript
  into the focused app.
- **Redaction** — every conversation turn passes through a `Redactor` before it is
  stored.
- **Fluent HUD** — a floating, Mica-effect Tauri window with listening state,
  transcript, waveform, tool calls, history and a tray manager.

## Architecture

```
┌─────────────────────────────┐   loopback WebSocket    ┌──────────────────────┐
│  Daemon (Python 3.11)        │  (token-authenticated) │  HUD (Tauri v2)       │
│  mic → VAD → wake word →     │◄──────────────────────►│  Mica HUD             │
│  STT → intent judge → LLM →  │                        │  waveform +           │
│  tool router → native/MCP    │                        │  transcript + tray    │
│  tools → TTS                  │                        │  dictation history    │
└─────────────────────────────┘                        └──────────────────────┘
```

- **Daemon** (`daemon/`, Python 3.11, asyncio) — microphone capture, VAD, wake
  word, Whisper STT, the Ollama agent loop, TTS, the dictation hotkey and the
  tool/MCP runtime. Subpackages: audio, input, ipc, llm, mcp, memory, nlu, router,
  security, stt, tools, tts, util, wake.
- **HUD** (`hud/`, Tauri v2 + Rust + Svelte 5) — a transparent, undecorated,
  always-on-top 380×620 window with Mica, listening state, live transcript,
  waveform, tool calls, conversation history and the tray manager.

The two processes talk over a loopback WebSocket on an OS-assigned port with a
per-run token. The daemon writes endpoint metadata to `ipc.json`, which the Rust
client reads. The HUD exposes three Tauri commands: `send_message`,
`get_daemon_status` and `send_text_message`.

## Quick start (from source)

1. Install [Ollama](https://ollama.com) and pull the default model:
   ```powershell
   ollama pull qwen3:4b
   ```
2. Install Python 3.11 and set up the daemon:
   ```powershell
   cd daemon
   python -m venv .venv
   .\.venv\Scripts\Activate.ps1
   pip install -e ".[dev]"
   blankslate --config ..\blankslate-data\config.json
   ```
   The CLI accepts `--config <path>` and `--log-level
   {DEBUG,INFO,WARNING,ERROR,CRITICAL}`.
3. Build and run the HUD:
   ```powershell
   cd ..\hud
   pnpm install
   pnpm tauri dev
   ```

> Both `hud/package-lock.json` and `hud/pnpm-lock.yaml` are committed, and
> `hud/package.json` has no `packageManager` field. The README uses pnpm; an npm
> workflow is equally plausible from the lockfiles. Pick one deliberately.

## Configuration

The daemon takes a JSON config file through `--config`. The data directory defaults
under `LOCALAPPDATA`. Environment names referenced by first-party code:
`LOCALAPPDATA`, `PATH`, `OLLAMA_HOST`, `ProgramFiles`, `BLANKSLATE_SMOKE_DIR` and
`BLANKSLATE_BUNDLE_ROOT`.

No `.env` or `.env.example` is tracked. The full `config.json` schema is not
documented in the repository.

## Data

Conversation history lives in the SQLite table
`turns(id, ts, role, content, source)`. Schema is created at runtime with
`CREATE TABLE IF NOT EXISTS`; there is no migration tooling. The HUD stores its
theme under the `blankslate-theme` `localStorage` key.

## Tests

```powershell
cd daemon
pytest
```

Pytest is configured with `testpaths=["tests"]` and `asyncio_mode=auto`. There are
22 test/smoke files under `daemon/tests`. No test run was performed for this
documentation.

## Packaging and release

The README documents this release process for a `v*` tag:

1. Freeze the Python daemon with PyInstaller
   (`daemon/pyinstaller/blankslate.spec`, copied by `daemon/build_daemon.ps1` into
   `hud/src-tauri/resources/daemon/`).
2. Build the HUD installer (`pnpm tauri build`) for MSI and NSIS.
3. Upload the installers as GitHub release assets.

The HUD launches the bundled daemon when present; otherwise it connects to an
externally running daemon. Build the frozen daemon locally with
`.\daemon\build_daemon.ps1`.

## Licensing

BlankSlate's original code is licensed under the **Apache License 2.0** (see
`LICENSE`).

The daemon's agentic core in `daemon/jarvis/` is a **vendored fork of
[isair/jarvis](https://github.com/isair/jarvis)**, used under the **Jarvis AI
Assistant License**, a non-commercial license (see `daemon/jarvis/LICENSE`). The
forked code and its derivatives must remain non-commercial; personal, educational
and research use is permitted, and the original notice is retained unmodified.

BlankSlate as distributed is therefore intended for **non-commercial, personal
use**. Commercial use requires a separate license from the upstream author.

Every other third-party dependency and bundled asset is audited in
[`THIRD_PARTY_NOTICES.md`](THIRD_PARTY_NOTICES.md) and `scripts/license_audit.py`.
Copyleft code is not imported or linked; GPL programs such as espeak-ng are invoked
only as separate, clearly labeled subprocesses.

## Documentation note

The previous README pointed readers to a `docs/` directory for architecture, MCP
configuration, wake-word training and the manual QA checklist. **No `docs/`
directory exists in this repository.** Use the source tree and
`THIRD_PARTY_NOTICES.md` instead.

## License

Apache-2.0 for original code; the vendored `daemon/jarvis/` tree keeps its own
non-commercial license.
