"""Voice gate driven by RNNoise's voice-activity probability (pure, tested).

RNNoise alone already removes most steady noise. Sharp keyboard and mouse
clicks between words can still leak through, so the optional gate fades the
mic out when nobody is speaking, with a short hold so word endings are kept.
"""

from __future__ import annotations

import math

import numpy as np


class VoiceGate:
    def __init__(
        self,
        frame_ms: float = 10.0,
        open_threshold: float = 0.6,
        close_threshold: float = 0.3,
        hold_ms: float = 250.0,
        attack_ms: float = 5.0,
        release_ms: float = 80.0,
        floor_db: float = -40.0,
    ) -> None:
        self.open_threshold = open_threshold
        self.close_threshold = close_threshold
        self.hold_frames = max(1, int(round(hold_ms / frame_ms)))
        self.attack = 1.0 - math.exp(-frame_ms / max(attack_ms, 0.1))
        self.release = 1.0 - math.exp(-frame_ms / max(release_ms, 0.1))
        self.floor = 10 ** (floor_db / 20.0)
        self.gain = self.floor
        self._open = False
        self._hold = 0

    def target(self, prob: float) -> float:
        if prob >= self.open_threshold:
            self._open = True
            self._hold = self.hold_frames
        elif self._open:
            if prob < self.close_threshold:
                self._hold -= 1
                if self._hold <= 0:
                    self._open = False
            else:
                self._hold = self.hold_frames
        return 1.0 if self._open else self.floor

    def apply(self, frame: np.ndarray, prob: float) -> np.ndarray:
        start = self.gain
        tgt = self.target(prob)
        coeff = self.attack if tgt > self.gain else self.release
        self.gain = self.gain + (tgt - self.gain) * coeff
        # Linear ramp across the frame avoids zipper noise.
        ramp = np.linspace(start, self.gain, num=len(frame), dtype=np.float32)
        return frame * ramp
