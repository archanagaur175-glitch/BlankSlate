"""Drop-in replacement for the upstream ``desktop_app.face_widget`` contract.

Upstream code calls ``get_jarvis_state().set_state(JarvisState.X)`` to drive the
PyQt face. In BlankSlate those calls are rerouted through the loopback IPC hub
so the Tauri HUD receives ``state`` events instead.
"""

from .ipc import broadcast_state


class JarvisState:
    LISTENING = "listening"
    IDLE = "idle"
    THINKING = "thinking"
    DICTATING = "dictating"
    DICTATION_PROCESSING = "dictating"
    SPEAKING = "speaking"


class _FaceState:
    def set_state(self, state: str) -> None:
        broadcast_state(state)


_face_state = _FaceState()


def get_jarvis_state() -> _FaceState:
    return _face_state
