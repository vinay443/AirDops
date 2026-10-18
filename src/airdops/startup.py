"""'Start with Windows' via the per-user Run key (no admin rights needed)."""

from __future__ import annotations

import logging
import sys
from pathlib import Path

log = logging.getLogger(__name__)

_RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
_NAME = "AirDops"


def command() -> str:
    if getattr(sys, "frozen", False):
        return f'"{sys.executable}" --background'
    pythonw = Path(sys.executable).with_name("pythonw.exe")
    exe = pythonw if pythonw.exists() else Path(sys.executable)
    return f'"{exe}" -m airdops --background'


def is_enabled() -> bool:
    import winreg

    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, _RUN_KEY) as key:
            winreg.QueryValueEx(key, _NAME)
            return True
    except OSError:
        return False


def set_enabled(enabled: bool) -> bool:
    import winreg

    try:
        with winreg.CreateKeyEx(winreg.HKEY_CURRENT_USER, _RUN_KEY, 0, winreg.KEY_SET_VALUE) as key:
            if enabled:
                winreg.SetValueEx(key, _NAME, 0, winreg.REG_SZ, command())
            else:
                try:
                    winreg.DeleteValue(key, _NAME)
                except FileNotFoundError:
                    pass
        return True
    except OSError as exc:
        log.warning("could not update startup entry: %r", exc)
        return False
