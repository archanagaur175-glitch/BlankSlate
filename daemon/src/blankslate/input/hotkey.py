"""Global hotkey registration for push-to-talk dictation.

The keyboard library hooks the OS key state from a background thread, so the
callbacks it invokes are marshalled to the daemon's asyncio loop by the caller
(the ``on_start``/``on_stop`` hooks are expected to be thread-safe). The module
is isolated so it can be unit-tested with a fake ``keyboard`` backend.
"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


def _load_keyboard():
    import keyboard

    return keyboard


class HotkeyManager:
    """Registers a global hotkey that drives a push-to-talk session.

    In ``hold_to_talk`` mode the hotkey fires ``on_start`` on press and
    ``on_stop`` on release. In toggle mode a single press toggles between
    start and stop so a hotkey can begin/end dictation without holding it.
    """

    def __init__(
        self,
        hotkey: str,
        on_start,
        on_stop,
        hold_to_talk: bool = True,
        keyboard_mod=None,
    ) -> None:
        self.hotkey = hotkey
        self.on_start = on_start
        self.on_stop = on_stop
        self.hold_to_talk = hold_to_talk
        self._kb = keyboard_mod if keyboard_mod is not None else _load_keyboard()
        self._handles: list[int] = []
        self._active = False

    # ------------------------------------------------------------------ lifecycle

    def start(self) -> None:
        if not self.hotkey:
            return
        try:
            if self.hold_to_talk:
                self._handles.append(self._kb.add_hotkey(self.hotkey, self._start))
                self._handles.append(
                    self._kb.add_hotkey(self.hotkey, self._stop, trigger_on_release=True)
                )
            else:
                self._active = False
                self._handles.append(self._kb.add_hotkey(self.hotkey, self._toggle))
        except Exception as exc:  # noqa: BLE001
            logger.warning("hotkey registration failed: %s", exc)

    def stop(self) -> None:
        for handle in self._handles:
            try:
                self._kb.remove_hotkey(handle)
            except Exception:  # noqa: BLE001
                pass
        self._handles.clear()

    # ----------------------------------------------------------------- callbacks

    def _start(self) -> None:
        self.on_start()

    def _stop(self) -> None:
        self.on_stop()

    def _toggle(self) -> None:
        if self._active:
            self._active = False
            self.on_stop()
        else:
            self._active = True
            self.on_start()
