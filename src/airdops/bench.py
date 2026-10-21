"""``AirDops.exe --bench REPORT``: measure startup time, idle CPU and memory.

Starts the real app (engine, tray icon, Bluetooth monitor), then:

1. time from process creation to the tray icon being shown,
2. memory and CPU while idle in the tray,
3. memory and CPU with the panel open,
4. the realtime cost of noise suppression per 10 ms frame,

writes the numbers to REPORT and quits (undoing any audio changes, as usual).
CI runs it on the built exe; run it on your own PC for real-hardware numbers.
"""

from __future__ import annotations

import ctypes
import sys
import time
from ctypes import wintypes
from pathlib import Path

IDLE_SECONDS = 30.0
PANEL_SETTLE_SECONDS = 1.5  # let the fade-in finish first
PANEL_SECONDS = 10.0


class _MemCounters(ctypes.Structure):
    _fields_ = [
        ("cb", wintypes.DWORD),
        ("PageFaultCount", wintypes.DWORD),
        ("PeakWorkingSetSize", ctypes.c_size_t),
        ("WorkingSetSize", ctypes.c_size_t),
        ("QuotaPeakPagedPoolUsage", ctypes.c_size_t),
        ("QuotaPagedPoolUsage", ctypes.c_size_t),
        ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t),
        ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
        ("PagefileUsage", ctypes.c_size_t),
        ("PeakPagefileUsage", ctypes.c_size_t),
        ("PrivateUsage", ctypes.c_size_t),
    ]


def _kernel32():
    k = ctypes.WinDLL("kernel32")
    k.GetCurrentProcess.restype = wintypes.HANDLE
    k.GetCurrentProcess.argtypes = []
    pft = ctypes.POINTER(wintypes.FILETIME)
    k.GetProcessTimes.argtypes = [wintypes.HANDLE, pft, pft, pft, pft]
    k.GetProcessTimes.restype = wintypes.BOOL
    k.GetSystemTimePreciseAsFileTime.argtypes = [pft]
    k.GetSystemTimePreciseAsFileTime.restype = None
    k.K32GetProcessMemoryInfo.argtypes = [wintypes.HANDLE, ctypes.POINTER(_MemCounters), wintypes.DWORD]
    k.K32GetProcessMemoryInfo.restype = wintypes.BOOL
    return k


def _filetime(ft: wintypes.FILETIME) -> float:
    return ((ft.dwHighDateTime << 32) | ft.dwLowDateTime) / 1e7  # seconds


def process_times() -> tuple[float, float]:
    """(seconds since this process was created, CPU seconds used so far)."""
    k = _kernel32()
    create, exit_, kern, user, now = (wintypes.FILETIME() for _ in range(5))
    if not k.GetProcessTimes(k.GetCurrentProcess(), ctypes.byref(create), ctypes.byref(exit_), ctypes.byref(kern), ctypes.byref(user)):
        raise OSError("GetProcessTimes failed")
    k.GetSystemTimePreciseAsFileTime(ctypes.byref(now))
    return _filetime(now) - _filetime(create), _filetime(kern) + _filetime(user)


def memory_mb() -> tuple[float, float]:
    """(working set MB, private bytes MB)."""
    c = _MemCounters()
    c.cb = ctypes.sizeof(c)
    k = _kernel32()
    if not k.K32GetProcessMemoryInfo(k.GetCurrentProcess(), ctypes.byref(c), c.cb):
        raise OSError("GetProcessMemoryInfo failed")
    return c.WorkingSetSize / 1e6, c.PrivateUsage / 1e6


def thread_count() -> int:
    import threading

    return threading.active_count()


def run(report: str) -> int:
    from PySide6.QtCore import QTimer

    from .core import Core
    from .ui.shell import Shell

    lines: list[str] = []

    def add(line: str) -> None:
        lines.append(line)

    core = Core()
    core.settings.onboarded = True  # no welcome sheet during the measurement
    shell = Shell(core, background=True)
    state: dict[str, float] = {}

    def at_tray() -> None:
        since_start, _ = process_times()
        add(f"startup: tray icon shown {since_start * 1000:.0f} ms after the process started")
        QTimer.singleShot(3000, idle_start)

    def idle_start() -> None:
        ws, priv = memory_mb()
        add(f"idle memory: working set {ws:.0f} MB, private {priv:.0f} MB, {thread_count()} Python threads")
        state["t0"], state["cpu0"] = time.perf_counter(), process_times()[1]
        QTimer.singleShot(int(IDLE_SECONDS * 1000), idle_end)

    def idle_end() -> None:
        dt = time.perf_counter() - state["t0"]
        cpu = process_times()[1] - state["cpu0"]
        add(f"idle CPU: {cpu / dt * 100:.2f}% of one core over {dt:.0f} s (Windows counts CPU time in 15.6 ms steps)")
        shell._open_panel()
        QTimer.singleShot(int(PANEL_SETTLE_SECONDS * 1000), panel_start)

    def panel_start() -> None:
        state["t1"], state["cpu1"] = time.perf_counter(), process_times()[1]
        QTimer.singleShot(int(PANEL_SECONDS * 1000), panel_end)

    def panel_end() -> None:
        dt = time.perf_counter() - state["t1"]
        cpu = process_times()[1] - state["cpu1"]
        ws, priv = memory_mb()
        add(f"panel open: working set {ws:.0f} MB, private {priv:.0f} MB, CPU {cpu / dt * 100:.2f}% of one core")
        shell.panel.hide()
        try:
            from .denoise import rnnoise

            if rnnoise.available():
                add(f"noise suppression: {rnnoise.benchmark(500):.0f} us per 10 ms frame")
        except Exception as exc:  # noqa: BLE001
            add(f"noise suppression: unavailable ({exc})")
        Path(report).write_text("\n".join(lines) + "\n", encoding="utf-8")
        shell.quit()

    QTimer.singleShot(0, at_tray)
    return shell.run()


if __name__ == "__main__":  # pragma: no cover
    sys.exit(run(sys.argv[1]))
