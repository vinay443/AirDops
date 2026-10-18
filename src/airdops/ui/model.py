"""What the UI shows - a plain snapshot built by the core, no Qt here."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional


@dataclass(frozen=True)
class ViewState:
    connected: bool = False
    name: str = "AirPods"
    mode: str = "game"  # "game" | "call"
    battery_known: bool = False
    single_unit: bool = False
    left: Optional[int] = None
    right: Optional[int] = None
    case: Optional[int] = None
    left_charging: bool = False
    right_charging: bool = False
    case_charging: bool = False
    left_in_ear: bool = False
    right_in_ear: bool = False
    mic_name: str = ""
    mics: tuple[str, ...] = field(default_factory=tuple)
    preferred_mic: str = ""
    cable_installed: bool = False
    ns_active: bool = False
    hfp_blocked: bool = False
    note: str = ""
    # settings
    noise_suppression: bool = True
    voice_gate: bool = False
    mic_gain_db: float = 0.0
    auto_pause_trigger: str = "one"
    hotkey: str = "Ctrl+Alt+M"
    prevent_ducking: bool = True
    auto_pause: bool = True
    battery_notifications: bool = True
    start_with_windows: bool = False
    version: str = ""

    @property
    def lowest(self) -> Optional[int]:
        vals = [v for v in (self.left, self.right) if v is not None]
        return min(vals) if vals else None

    def status_line(self) -> str:
        if not self.connected:
            return "Not Connected"
        mode = "Game Mode" if self.mode == "game" else "Call Mode"
        if self.left_in_ear or self.right_in_ear:
            return f"Connected · In Use · {mode}"
        return f"Connected · {mode}"

    def mode_caption(self) -> str:
        if self.mode == "game":
            if not self.connected:
                return "When your AirPods connect, sound stays full quality and your laptop mic is used."
            if self.hfp_blocked:
                return "Full-quality stereo sound. Apps can't switch your AirPods into call mode."
            return "Full-quality stereo sound with your laptop mic."
        return "Uses the AirPods microphone. Windows lowers sound quality while the mic is in use."
