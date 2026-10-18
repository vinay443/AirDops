"""In-ear detection -> play/pause decisions (pure logic, unit tested).

Mirrors what macOS does: take a bud out and media pauses, put it back and
media resumes - but only if we were the ones who paused it.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

PAUSE = "pause"
RESUME = "resume"


@dataclass
class EarDetector:
    trigger: str = "one"  # "one": pause when either bud leaves; "both": only when both do
    debounce_s: float = 1.0
    stale_after_s: float = 8.0

    _worn: Optional[bool] = field(default=None, init=False)
    _candidate: Optional[bool] = field(default=None, init=False)
    _candidate_since: float = field(default=0.0, init=False)
    _last_seen: float = field(default=0.0, init=False)
    paused_by_us: bool = field(default=False, init=False)

    def _is_worn(self, left: bool, right: bool, single_unit: bool) -> bool:
        if single_unit:
            return left or right
        if self.trigger == "both":
            return left or right
        return left and right

    def reset(self) -> None:
        self._worn = None
        self._candidate = None
        self.paused_by_us = False

    def update(self, left: bool, right: bool, now: float, single_unit: bool = False) -> Optional[str]:
        """Feed a sensor reading. Returns PAUSE, RESUME or None."""
        if self._last_seen and now - self._last_seen > self.stale_after_s:
            # Data gap (out of range / scanner hiccup): start fresh, never act on it.
            self._worn = None
            self._candidate = None
        self._last_seen = now

        worn = self._is_worn(left, right, single_unit)
        if self._worn is None:
            self._worn = worn
            return None
        if worn == self._worn:
            self._candidate = None
            return None
        if self._candidate != worn:
            self._candidate = worn
            self._candidate_since = now
            return None
        if now - self._candidate_since < self.debounce_s:
            return None

        self._worn = worn
        self._candidate = None
        if not worn:
            return PAUSE
        if self.paused_by_us:
            return RESUME
        return None
