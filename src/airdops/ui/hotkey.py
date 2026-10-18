"""System-wide keyboard shortcut (Windows RegisterHotKey), e.g. Ctrl+Alt+M.

The hotkey is registered to a hidden native window owned by the Qt main
thread; a native event filter picks up WM_HOTKEY for it.
"""

from __future__ import annotations

import ctypes
import logging
import sys
from typing import Callable, Optional

from PySide6.QtCore import QAbstractNativeEventFilter, QCoreApplication
from PySide6.QtWidgets import QWidget

log = logging.getLogger(__name__)

MOD_ALT, MOD_CONTROL, MOD_SHIFT, MOD_WIN, MOD_NOREPEAT = 0x1, 0x2, 0x4, 0x8, 0x4000
WM_HOTKEY = 0x0312
_HOTKEY_ID = 0xAD01

_MODS = {"ctrl": MOD_CONTROL, "control": MOD_CONTROL, "alt": MOD_ALT, "shift": MOD_SHIFT, "win": MOD_WIN}


def parse(spec: str) -> Optional[tuple[int, int]]:
    """'Ctrl+Alt+M' -> (modifiers, virtual-key code). None if invalid/empty.

    At least one of Ctrl/Alt/Win is required so plain typing is never stolen.
    """
    parts = [p.strip().lower() for p in spec.replace(" ", "").split("+") if p.strip()]
    if len(parts) < 2:
        return None
    mods = 0
    for p in parts[:-1]:
        if p not in _MODS:
            return None
        mods |= _MODS[p]
    if not mods & (MOD_CONTROL | MOD_ALT | MOD_WIN):
        return None
    key = parts[-1]
    if len(key) == 1 and key.isalnum():
        vk = ord(key.upper())
    elif key.startswith("f") and key[1:].isdigit() and 1 <= int(key[1:]) <= 24:
        vk = 0x70 + int(key[1:]) - 1
    else:
        return None
    return mods, vk


class _Filter(QAbstractNativeEventFilter):
    def __init__(self, hwnd: int, callback: Callable[[], None]) -> None:
        super().__init__()
        self.hwnd = hwnd
        self.callback = callback

    def nativeEventFilter(self, event_type, message):  # noqa: N802
        if event_type in (b"windows_generic_MSG", "windows_generic_MSG"):
            from ctypes import wintypes

            msg = wintypes.MSG.from_address(int(message))
            if msg.message == WM_HOTKEY and msg.wParam == _HOTKEY_ID:
                try:
                    self.callback()
                except Exception:  # noqa: BLE001
                    log.exception("hotkey handler failed")
                return True, 0
        return False, 0


class GlobalHotkey:
    def __init__(self, callback: Callable[[], None]) -> None:
        self.callback = callback
        self._window: Optional[QWidget] = None
        self._filter: Optional[_Filter] = None
        self._registered = False

    def register(self, spec: str) -> bool:
        self.unregister()
        if sys.platform != "win32" or not spec:
            return False
        parsed = parse(spec)
        if parsed is None:
            log.warning("invalid hotkey %r", spec)
            return False
        mods, vk = parsed
        if self._window is None:
            self._window = QWidget()
            self._window.setWindowTitle("AirDops hotkey")
        hwnd = int(self._window.winId())  # creates the native window without showing it
        user32 = ctypes.windll.user32
        if not user32.RegisterHotKey(ctypes.c_void_p(hwnd), _HOTKEY_ID, mods | MOD_NOREPEAT, vk):
            log.warning("hotkey %s is already used by another app", spec)
            return False
        self._filter = _Filter(hwnd, self.callback)
        QCoreApplication.instance().installNativeEventFilter(self._filter)
        self._registered = True
        log.info("global hotkey %s registered", spec)
        return True

    def unregister(self) -> None:
        if self._registered and self._window is not None:
            ctypes.windll.user32.UnregisterHotKey(ctypes.c_void_p(int(self._window.winId())), _HOTKEY_ID)
        if self._filter is not None:
            QCoreApplication.instance().removeNativeEventFilter(self._filter)
        self._filter = None
        self._registered = False
