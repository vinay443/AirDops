"""Minimal ctypes binding for RNNoise (Xiph.org, BSD-3-Clause).

RNNoise is a small recurrent neural network that removes background noise
(keyboard, fans, room hum) from speech in real time. It works on 10 ms frames
of 48 kHz mono audio, with samples in 16-bit range stored as float32.

The DLL is not committed to the repository; ``scripts/fetch_rnnoise.py``
downloads it from a pinned, hash-verified PyPI wheel at build time.
"""

from __future__ import annotations

import ctypes
import os
import sys
from pathlib import Path
from typing import Optional

import numpy as np

SAMPLE_RATE = 48000
FRAME_SIZE = 480

_LIB_NAMES = {
    "win32": "rnnoise.dll",
    "darwin": "librnnoise.dylib",
}


def _candidate_paths() -> list[Path]:
    name = _LIB_NAMES.get(sys.platform, "librnnoise.so")
    paths: list[Path] = []
    env = os.environ.get("AIRDOPS_RNNOISE")
    if env:
        paths.append(Path(env))
    meipass = getattr(sys, "_MEIPASS", None)
    if meipass:
        paths.append(Path(meipass) / "airdops" / "_vendor" / name)
    paths.append(Path(__file__).resolve().parent.parent / "_vendor" / name)
    return paths


_lib: Optional[ctypes.CDLL] = None


def load() -> ctypes.CDLL:
    global _lib
    if _lib is not None:
        return _lib
    for path in _candidate_paths():
        if path.is_file():
            lib = ctypes.CDLL(str(path))
            lib.rnnoise_create.argtypes = [ctypes.c_void_p]
            lib.rnnoise_create.restype = ctypes.c_void_p
            lib.rnnoise_destroy.argtypes = [ctypes.c_void_p]
            lib.rnnoise_destroy.restype = None
            lib.rnnoise_process_frame.argtypes = [
                ctypes.c_void_p,
                ctypes.POINTER(ctypes.c_float),
                ctypes.POINTER(ctypes.c_float),
            ]
            lib.rnnoise_process_frame.restype = ctypes.c_float
            lib.rnnoise_get_frame_size.restype = ctypes.c_int
            if lib.rnnoise_get_frame_size() != FRAME_SIZE:
                raise OSError("unexpected RNNoise frame size")
            _lib = lib
            return lib
    raise FileNotFoundError("RNNoise library not found (run scripts/fetch_rnnoise.py)")


def available() -> bool:
    try:
        load()
        return True
    except (OSError, FileNotFoundError):
        return False


class Denoiser:
    """One RNNoise state = one mono channel."""

    def __init__(self) -> None:
        self._lib = load()
        self._state = self._lib.rnnoise_create(None)
        if not self._state:
            raise MemoryError("rnnoise_create failed")
        self._buf = np.zeros(FRAME_SIZE, dtype=np.float32)
        self._ptr = self._buf.ctypes.data_as(ctypes.POINTER(ctypes.c_float))

    def process(self, frame: np.ndarray) -> tuple[np.ndarray, float]:
        """Denoise one 480-sample frame of float audio in [-1, 1].

        Returns (clean frame in [-1, 1], voice probability 0..1).
        """
        n = min(len(frame), FRAME_SIZE)
        self._buf[:n] = frame[:n] * 32767.0
        if n < FRAME_SIZE:
            self._buf[n:] = 0.0
        prob = float(self._lib.rnnoise_process_frame(self._state, self._ptr, self._ptr))
        out = self._buf[:n] * (1.0 / 32767.0)
        return out, prob

    def close(self) -> None:
        if self._state:
            self._lib.rnnoise_destroy(self._state)
            self._state = None

    def __del__(self) -> None:  # pragma: no cover
        try:
            self.close()
        except Exception:
            pass
