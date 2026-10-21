"""Single-instance "open the panel" signal, using a Win32 named event.

The first AirDops creates an auto-reset event in the per-session ``Local\\``
namespace and waits on it from a small thread. Launching AirDops again just
sets the event, and the running copy opens its panel. No data is exchanged,
so there is nothing to parse, and nothing here needs Qt (a second launch exits
almost instantly). On other platforms these are no-ops.
"""

from __future__ import annotations

import ctypes
import logging
import sys
import threading
from typing import Callable, Optional

log = logging.getLogger(__name__)

EVENT_NAME = "Local\\AirDops-show-panel"
_EVENT_MODIFY_STATE = 0x0002
_SYNCHRONIZE = 0x00100000
_WAIT_OBJECT_0 = 0
_INFINITE = 0xFFFFFFFF


def _kernel32():
    k = ctypes.WinDLL("kernel32", use_last_error=True)
    HANDLE, BOOL, DWORD, LPCWSTR = ctypes.c_void_p, ctypes.c_int, ctypes.c_uint32, ctypes.c_wchar_p
    k.CreateEventW.argtypes = [ctypes.c_void_p, BOOL, BOOL, LPCWSTR]
    k.CreateEventW.restype = HANDLE
    k.OpenEventW.argtypes = [DWORD, BOOL, LPCWSTR]
    k.OpenEventW.restype = HANDLE
    k.SetEvent.argtypes = [HANDLE]
    k.SetEvent.restype = BOOL
    k.CloseHandle.argtypes = [HANDLE]
    k.CloseHandle.restype = BOOL
    k.WaitForMultipleObjects.argtypes = [DWORD, ctypes.POINTER(HANDLE), BOOL, DWORD]
    k.WaitForMultipleObjects.restype = DWORD
    return k


def signal_running_instance() -> bool:
    """Ask an already-running AirDops to open its panel. True if one was found."""
    if sys.platform != "win32":
        return False
    k = _kernel32()
    handle = k.OpenEventW(_EVENT_MODIFY_STATE | _SYNCHRONIZE, False, EVENT_NAME)
    if not handle:
        return False
    try:
        return bool(k.SetEvent(handle))
    finally:
        k.CloseHandle(handle)


class ShowListener:
    """Calls ``on_show`` (from a background thread) whenever another launch signals."""

    def __init__(self, on_show: Callable[[], None]) -> None:
        self._on_show = on_show
        self._k = None
        self._event = None
        self._stop = None
        self._thread: Optional[threading.Thread] = None

    def start(self) -> bool:
        if sys.platform != "win32":
            return False
        k = self._k = _kernel32()
        self._event = k.CreateEventW(None, False, False, EVENT_NAME)
        self._stop = k.CreateEventW(None, True, False, None)
        if not self._event or not self._stop:
            log.warning("show-panel event unavailable (error %d)", ctypes.get_last_error())
            self.stop()
            return False
        self._thread = threading.Thread(target=self._run, name="airdops-show", daemon=True)
        self._thread.start()
        return True

    def _run(self) -> None:
        k = self._k
        handles = (ctypes.c_void_p * 2)(self._event, self._stop)
        while True:
            r = k.WaitForMultipleObjects(2, handles, False, _INFINITE)
            if r == _WAIT_OBJECT_0:
                try:
                    self._on_show()
                except Exception:  # noqa: BLE001
                    log.exception("show-panel callback failed")
            else:  # stop event, or an error
                return

    def stop(self) -> None:
        k = self._k
        if k is None:
            return
        if self._stop:
            k.SetEvent(self._stop)
        if self._thread is not None:
            self._thread.join(timeout=2)
            self._thread = None
        for name in ("_event", "_stop"):
            h = getattr(self, name)
            if h:
                k.CloseHandle(h)
                setattr(self, name, None)
