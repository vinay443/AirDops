"""Settings and runtime state, stored only on this PC.

* settings.json  (%APPDATA%\\AirDops)       - user preferences
* state.json     (%LOCALAPPDATA%\\AirDops)  - what we changed, so it can be undone
                                             even after a crash
* logs\\          (%LOCALAPPDATA%\\AirDops)  - rotating log, device names only

Nothing here is ever sent anywhere: AirDops makes no network connections.
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
import threading
from dataclasses import asdict, dataclass, field, fields
from pathlib import Path
from typing import Any, Optional

APP_NAME = "AirDops"


def _base(env: str) -> Path:
    root = os.environ.get(env)
    if sys.platform == "win32" and root:
        return Path(root) / APP_NAME
    return Path.home() / f".{APP_NAME.lower()}"


def settings_dir() -> Path:
    return _base("APPDATA")


def data_dir() -> Path:
    return _base("LOCALAPPDATA")


def log_dir() -> Path:
    return data_dir() / "logs"


@dataclass
class Settings:
    # Substrings that identify your AirPods in Windows sound device names.
    device_keywords: list[str] = field(default_factory=lambda: ["AirPods"])
    # "game": full-quality AirPods sound + other mic.  "call": use AirPods mic.
    mode: str = "game"
    # Substring of the mic to use in game mode. Empty = pick the built-in mic.
    preferred_mic: str = ""
    # AI noise suppression on the laptop mic (needs the free VB-Cable driver).
    noise_suppression: bool = True
    # Also hard-gate the mic between words (kills keyboard clicks completely).
    voice_gate: bool = False
    # Extra mic gain in dB applied after noise suppression (laptop mics are quiet).
    mic_gain_db: float = 0.0
    # Pause media when a bud is taken out, resume when it goes back in.
    auto_pause: bool = True
    # "one" = pause when either bud is removed (like a Mac), "both" = only when both are.
    auto_pause_trigger: str = "one"
    # Stop Windows from turning game audio down while voice chat is open.
    prevent_ducking: bool = True
    # Battery level from the AirPods' Bluetooth LE broadcast.
    battery_monitor: bool = True
    battery_notifications: bool = True
    low_battery_percent: int = 20
    # Ignore AirPods broadcasts weaker than this (filters out other people's AirPods).
    ble_min_rssi: int = -70
    poll_seconds: float = 2.0

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> "Settings":
        known = {f.name: f for f in fields(cls)}
        default = cls()
        values: dict[str, Any] = {}
        for name, value in raw.items():
            if name not in known:
                continue
            expected = type(getattr(default, name))
            if expected is float and isinstance(value, int) and not isinstance(value, bool):
                value = float(value)
            if isinstance(value, expected) and not (expected is int and isinstance(value, bool)):
                values[name] = value
        s = cls(**values)
        if s.mode not in ("game", "call"):
            s.mode = "game"
        if s.auto_pause_trigger not in ("one", "both"):
            s.auto_pause_trigger = "one"
        s.device_keywords = [k for k in s.device_keywords if isinstance(k, str) and k.strip()] or ["AirPods"]
        s.low_battery_percent = max(5, min(50, s.low_battery_percent))
        s.mic_gain_db = max(-12.0, min(24.0, s.mic_gain_db))
        s.poll_seconds = max(0.5, min(10.0, s.poll_seconds))
        return s


@dataclass
class State:
    """Things AirDops changed and must put back."""

    disabled_endpoints: list[str] = field(default_factory=list)
    # Defaults before AirDops touched them: {"render": id, "capture": id, ...}
    saved_defaults: dict[str, str] = field(default_factory=dict)
    # Original UserDuckingPreference (None = value did not exist)
    ducking_changed: bool = False
    ducking_original: Optional[int] = None

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> "State":
        s = cls()
        if isinstance(raw.get("disabled_endpoints"), list):
            s.disabled_endpoints = [x for x in raw["disabled_endpoints"] if isinstance(x, str)]
        if isinstance(raw.get("saved_defaults"), dict):
            s.saved_defaults = {
                k: v for k, v in raw["saved_defaults"].items() if isinstance(k, str) and isinstance(v, str)
            }
        s.ducking_changed = bool(raw.get("ducking_changed", False))
        orig = raw.get("ducking_original")
        s.ducking_original = orig if isinstance(orig, int) and not isinstance(orig, bool) else None
        return s


_lock = threading.Lock()


def _read_json(path: Path) -> dict[str, Any]:
    try:
        with open(path, "r", encoding="utf-8") as fh:
            data = json.load(fh)
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def _write_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=path.name, suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(data, fh, indent=2)
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def settings_path() -> Path:
    return settings_dir() / "settings.json"


def state_path() -> Path:
    return data_dir() / "state.json"


def load_settings() -> Settings:
    with _lock:
        path = settings_path()
        s = Settings.from_dict(_read_json(path))
        if not path.exists():
            _write_json(path, asdict(s))
        return s


def save_settings(s: Settings) -> None:
    with _lock:
        _write_json(settings_path(), asdict(s))


def load_state() -> State:
    with _lock:
        return State.from_dict(_read_json(state_path()))


def save_state(s: State) -> None:
    with _lock:
        _write_json(state_path(), asdict(s))
