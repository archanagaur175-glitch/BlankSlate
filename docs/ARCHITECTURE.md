# Architecture

Static description of the BlankSlate code at HEAD. No daemon, HUD or model was run.

## Components

```
daemon/   Python 3.11 asyncio package `blankslate`
hud/      Tauri v2 app: Svelte 5 frontend + Rust bridge
```

The daemon owns the microphone and the assistant loop. The HUD is a thin desktop
client that sends text and renders state.

## Daemon pipeline

Documented flow:

```
mic → VAD → wake word → STT → intent judge → LLM →
tool router → native/MCP tools → TTS
```

Package responsibilities (`daemon/src/blankslate/`):

| Subpackage | Responsibility |
| --- | --- |
| `audio`, `input` | Microphone capture and input handling |
| `wake` | Wake-word detection |
| `stt` | Whisper transcription |
| `nlu` | Intent handling |
| `llm` | Ollama client and agentic loop |
| `router` | Tool routing |
| `tools`, `mcp` | Native tools and MCP runtime |
| `tts` | Text-to-speech |
| `memory` | Conversation storage and redaction |
| `security` | Security helpers |
| `ipc` | Loopback WebSocket server |
| `util` | Shared utilities |

Entry point: console script `blankslate` → `daemon/src/blankslate/__main__.py`
`main()`, which loads and validates config, sets up a rotating file log at
`logs/daemon.log`, installs exception hooks and constructs `DaemonApp(config)`.

CLI flags: `--config <path>` and `--log-level {DEBUG,INFO,WARNING,ERROR,CRITICAL}`.
There is no REST or GraphQL API.

### Vendored agentic core

`daemon/jarvis/` is a vendored fork of isair/jarvis under a non-commercial license.
Its environment variables (`JARVIS_*`, `XDG_CONFIG_HOME`, `SHELL`, thread-count
variables, `HF_HUB_DISABLE_SYMLINKS_WARNING`) belong to that vendored tree and are
not part of the original BlankSlate surface. See the repository README and
`daemon/jarvis/LICENSE`.

## IPC

- Loopback-only WebSocket on an OS-assigned port.
- Per-run token authentication.
- Events are broadcast to all connected clients.
- Endpoint metadata is written to `ipc.json`, which the Rust client reads.

The HUD exposes three Tauri commands:

| Command | Role |
| --- | --- |
| `send_message` | Send a voice/text message to the daemon |
| `get_daemon_status` | Report daemon connectivity |
| `send_text_message` | Send typed text |

## HUD / Tauri boundary

- Frontend: `hud/index.html` → `hud/src/main.ts` → `hud/src/App.svelte`.
- Native: `hud/src-tauri/src/main.rs` → `hud/src-tauri/src/lib.rs`.
- Window: transparent, undecorated, always-on-top, 380×620, Mica effect.
- Frontend stack: Svelte 5, Vite 6, TypeScript 5.6, Tauri API/CLI v2.
- Theme persistence: `blankslate-theme` in `localStorage`.

## Memory

SQLite table:

```sql
turns(id, ts, role, content, source)
```

Every turn passes through a `Redactor` before insert. The schema is created with
`CREATE TABLE IF NOT EXISTS`; there is no migration tooling.

## Configuration

The config is a JSON file passed with `--config`. The data directory defaults under
`LOCALAPPDATA`. First-party environment names: `LOCALAPPDATA`, `PATH`,
`OLLAMA_HOST`, `ProgramFiles`, `BLANKSLATE_SMOKE_DIR`, `BLANKSLATE_BUNDLE_ROOT`.

The complete `config.json` schema is not documented in the repository.

## Build, test and packaging

- Daemon: `pip install -e ".[dev]"`, then `blankslate --config <path>`.
- HUD: `pnpm install`, `pnpm tauri dev`.
- Tests: pytest with `testpaths=["tests"]` and `asyncio_mode=auto`; 22 test/smoke
  files under `daemon/tests`.
- Packaging: PyInstaller spec `daemon/pyinstaller/blankslate.spec`, copied by
  `daemon/build_daemon.ps1`; `pnpm tauri build` produces MSI and NSIS targets.

Both `hud/package-lock.json` and `hud/pnpm-lock.yaml` are committed, and
`hud/package.json` has no `packageManager` field.

## Unknowns

- The full `config.json` schema and keys.
- Which wake-word and STT model files are expected, and where they are stored.
- Whether the `docs/` directory referenced by the old README ever existed.
