# Third-party notices & license audit

BlankSlate is Apache-2.0. This file records every third-party dependency and
bundled asset, its license, and any policy flags. It is maintained by
`scripts/license_audit.py`, which fails CI if an unapproved license appears.

## License policy

- **Allowed (can be imported/linked/bundled):** MIT, Apache-2.0, BSD, PSF, HPND,
  ISC, Zlib, Python-2.0, Unicode-3.0, CC0, public domain.
- **Excluded (never imported, linked, or vendored):** GPL/AGPL code, source-
  available / non-commercial licenses (e.g. isair/jarvis).
- **External subprocess only (flagged):** GPL-3.0 helper *programs* such as
  espeak-ng (used by the Kokoro TTS phonemizer) are invoked as separate processes
  and distributed as clearly-labeled separate components with their own license
  text. They are never imported as libraries.

## Runtime dependencies

| Package | Version (pinned) | License | Flag |
|---|---|---|---|
| sounddevice | ~=0.4.6 | MIT | |
| numpy | >=1.26 | BSD-3-Clause | |
| webrtcvad | >=2.0.10 | BSD-3-Clause | |
| openwakeword | ~=0.6.0 | Apache-2.0 | unmaintained upstream (2024); isolated behind `WakeEngine` adapter |
| onnxruntime | >=1.16 | MIT | |
| faster-whisper | >=1.0 | MIT | |
| ctranslate2 | (via faster-whisper) | MIT | |
| websockets | >=12 | BSD-3-Clause | |
| httpx | >=0.27 | BSD-3-Clause | |
| mcp | >=2.0 | MIT | MCP Python SDK v2 |
| keyboard | >=0.13 | MIT | |
| pywin32 | >=306 | PSF | |
| comtypes | >=1.3 | MIT | |
| pycaw | >=20251023 | MIT | verify at build |
| pywinauto | >=0.4.11 | BSD-3-Clause | |
| Pillow | >=10 | HPND | |
| psutil | >=5.9 | BSD-3-Clause | |
| ddgs | >=9 | MIT | |

## Optional runtime dependencies

| Package | License | Notes |
|---|---|---|
| kokoro | Apache-2.0 | TTS model + lib (hexgrad) |
| misaki | Apache-2.0 | phonemizer (hexgrad) |
| torch (CPU) | BSD-3-Clause | runtime for Kokoro |
| soundfile | BSD-3-Clause | audio I/O for Kokoro |
| espeak-ng (system) | GPL-3.0 | **external subprocess only**, separate component |
| fastembed | Apache-2.0 | embedding fallback if Ollama absent |
| all-MiniLM-L6-v2 (model) | MIT | fallback embedding model |
| whisper models (base.en, etc.) | MIT | OpenAI Whisper weights |

## Bundled models & assets

| Asset | License | Source |
|---|---|---|
| openwakeword "hey jarvis" model | Apache-2.0 | openwakeword releases |
| Whisper base.en | MIT | OpenAI/whisper |
| Kokoro voice | Apache-2.0 | hexgrad/Kokoro-82M |
| Original HUD branding/icons/waveform | Apache-2.0 (ours) | assets/ |

## Explicitly excluded (design reference only)

| Project | License | Reason |
|---|---|---|
| isair/jarvis | source-available, non-commercial | reference-only, never copied |
| OHF-Voice/piper1-gpl | GPL-3.0 | copyleft; do not bundle |
| kokoro-onnx (lib) | MIT | transitively imports GPL-3.0 `phonemizer`/`espeakng-loader` |
| pynput | LGPL-3.0 | avoided; `keyboard` (MIT) used instead |

## Build-time tools

| Tool | License | Notes |
|---|---|---|
| PyInstaller | GPL-2.0-or-later WITH bootloader exception | exception permits redistributing produced binaries |
| Inno Setup / NSIS | freeware / zlib-ish | Tauri NSIS bundler used for the installer |
| Ruff | MIT | lint/format |
| Rust toolchain | MIT / Apache-2.0 | |
