"""BlankSlate daemon.

A local-first voice assistant for Windows 11: mic -> wake word -> STT -> local
LLM -> native/MCP tools -> TTS, with a Tauri HUD client connected over a
token-authenticated loopback WebSocket.
"""

__version__ = "0.1.0"
