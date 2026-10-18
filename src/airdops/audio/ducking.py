"""Windows "communications activity" ducking.

By default Windows turns every other sound down by 80% whenever an app opens
a voice-chat stream - which is exactly what happens in Discord mid-game. The
setting lives in the Sound control panel (Communications tab) and is stored at
HKCU\\Software\\Microsoft\\Multimedia\\Audio\\UserDuckingPreference:

    0 = mute other sounds, 1 = reduce by 80% (default), 2 = reduce by 50%, 3 = do nothing
"""

from __future__ import annotations

import logging
from typing import Optional, Tuple

log = logging.getLogger(__name__)

_KEY = r"Software\Microsoft\Multimedia\Audio"
_VALUE = "UserDuckingPreference"
DO_NOTHING = 3


def read() -> Tuple[bool, Optional[int]]:
    """Returns (exists, value)."""
    import winreg

    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, _KEY) as key:
            value, kind = winreg.QueryValueEx(key, _VALUE)
            if kind == winreg.REG_DWORD:
                return True, int(value)
            return True, None
    except FileNotFoundError:
        return False, None
    except OSError as exc:
        log.warning("could not read ducking preference: %r", exc)
        return False, None


def write(value: Optional[int]) -> bool:
    """Set the preference, or delete the value when ``value`` is None."""
    import winreg

    try:
        with winreg.CreateKeyEx(winreg.HKEY_CURRENT_USER, _KEY, 0, winreg.KEY_SET_VALUE) as key:
            if value is None:
                try:
                    winreg.DeleteValue(key, _VALUE)
                except FileNotFoundError:
                    pass
            else:
                winreg.SetValueEx(key, _VALUE, 0, winreg.REG_DWORD, int(value))
        return True
    except OSError as exc:
        log.warning("could not write ducking preference: %r", exc)
        return False
