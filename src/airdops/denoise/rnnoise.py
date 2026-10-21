"""Minimal ctypes binding for RNNoise (Xiph.org, BSD-3-Clause).

RNNoise is a small recurrent neural network that removes background noise
(keyboard, fans, room hum) from speech in real time. It works on 10 ms frames
of 48 kHz mono audio, with samples in 16-bit range stored as float32.

The library is not committed to the repository; ``scripts/build_rnnoise.py``
builds it from pinned, verified Xiph.org source at build time, together with
AirDops' per-frame helper (``native/airdops_dsp.c``). If an RNNoise build
without the helper is used, the same maths runs in pure Python instead.
"""

from __future__ import annotations

import ctypes
import math
import os
import random
import sys
import time
from array import array
from pathlib import Path
from typing import Optional, Sequence

SAMPLE_RATE = 48000
FRAME_SIZE = 480
_SCALE = 32767.0
_INV_SCALE = 1.0 / 32767.0

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
_has_dsp = False


def open_library(path: str | os.PathLike) -> tuple[ctypes.CDLL, bool]:
    """Load an RNNoise library and declare its functions.

    Returns (library, whether it contains the AirDops per-frame helper).
    """
    lib = ctypes.CDLL(str(path))
    lib.rnnoise_create.argtypes = [ctypes.c_void_p]
    lib.rnnoise_create.restype = ctypes.c_void_p
    lib.rnnoise_destroy.argtypes = [ctypes.c_void_p]
    lib.rnnoise_destroy.restype = None
    lib.rnnoise_process_frame.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p]
    lib.rnnoise_process_frame.restype = ctypes.c_float
    lib.rnnoise_get_frame_size.restype = ctypes.c_int
    if lib.rnnoise_get_frame_size() != FRAME_SIZE:
        raise OSError("unexpected RNNoise frame size")
    try:
        lib.airdops_denoise.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_int, ctypes.c_int, ctypes.c_void_p]
        lib.airdops_denoise.restype = ctypes.c_float
        lib.airdops_finish.argtypes = [
            ctypes.c_void_p, ctypes.c_int, ctypes.c_float, ctypes.c_float, ctypes.c_float,
            ctypes.c_void_p, ctypes.c_int,
        ]
        lib.airdops_finish.restype = ctypes.c_double
        return lib, True
    except AttributeError:  # a plain RNNoise build: use the Python fallback
        return lib, False


def library_path() -> Optional[Path]:
    """Path of the RNNoise library AirDops would load, if any."""
    return next((p for p in _candidate_paths() if p.is_file()), None)


def load() -> ctypes.CDLL:
    global _lib, _has_dsp
    if _lib is not None:
        return _lib
    for path in _candidate_paths():
        if path.is_file():
            _lib, _has_dsp = open_library(path)
            return _lib
    raise FileNotFoundError("RNNoise library not found (run scripts/build_rnnoise.py)")


def available() -> bool:
    try:
        load()
        return True
    except (OSError, FileNotFoundError):
        return False


def has_native_helper() -> bool:
    return available() and _has_dsp


def address(buf) -> int:
    """Address of a writable buffer (bytearray, ctypes array, sounddevice raw buffer)."""
    return ctypes.addressof(ctypes.c_char.from_buffer(buf))


def float_view(buf) -> memoryview:
    mv = memoryview(buf)
    if mv.format != "f":
        mv = mv.cast("B").cast("f")
    return mv


class Denoiser:
    """One RNNoise state = one mono channel."""

    def __init__(self, library: Optional[str] = None) -> None:
        """``library``: path of a specific RNNoise build (tests); default is the bundled one."""
        if library is None:
            self._lib = load()
            self._native = _has_dsp
        else:
            self._lib, self._native = open_library(library)
        self._state = self._lib.rnnoise_create(None)
        if not self._state:
            raise MemoryError("rnnoise_create failed")
        self._buf = (ctypes.c_float * FRAME_SIZE)()
        self._buf_addr = ctypes.addressof(self._buf)

    def process(self, frame: Sequence[float]) -> tuple[array, float]:
        """Denoise one frame (up to 480 samples) of float audio in [-1, 1].

        Returns (clean frame in [-1, 1] as ``array('f')``, voice probability 0..1).
        Convenient but not allocation-free; the realtime path uses :meth:`run`.
        """
        n = min(len(frame), FRAME_SIZE)
        buf = self._buf
        for i in range(n):
            buf[i] = frame[i] * _SCALE
        for i in range(n, FRAME_SIZE):
            buf[i] = 0.0
        prob = float(self._lib.rnnoise_process_frame(self._state, self._buf_addr, self._buf_addr))
        return array("f", [v * _INV_SCALE for v in buf[:n]]), prob

    def run(self, indata, outdata, frames: int, in_ch: int, out_ch: int, gate=None, gain: float = 1.0) -> tuple[float, float]:
        """Denoise one audio callback's worth of interleaved float32 audio.

        ``indata``/``outdata`` are writable buffers (sounddevice raw buffers).
        The mic is downmixed to mono, denoised, gated (``gate.step(prob)`` gives
        the gain ramp), amplified by ``gain``, clipped and copied to every
        output channel. Returns (sum of squares of the output, last voice prob).
        """
        sumsq = 0.0
        prob = 0.0
        if self._native:
            lib, st, buf = self._lib, self._state, self._buf_addr
            src, dst = address(indata), address(outdata)
            for start in range(0, frames, FRAME_SIZE):
                n = min(FRAME_SIZE, frames - start)
                prob = lib.airdops_denoise(st, src + start * in_ch * 4, in_ch, n, buf)
                g0, g1 = gate.step(prob) if gate is not None else (1.0, 1.0)
                sumsq += lib.airdops_finish(buf, n, g0, g1, gain, dst + start * out_ch * 4, out_ch)
            return sumsq, prob
        src, dst, buf = float_view(indata), float_view(outdata), self._buf
        for start in range(0, frames, FRAME_SIZE):
            n = min(FRAME_SIZE, frames - start)
            inv = _SCALE / in_ch
            base = start * in_ch
            for i in range(n):
                j = base + i * in_ch
                buf[i] = sum(src[j : j + in_ch]) * inv
            for i in range(n, FRAME_SIZE):
                buf[i] = 0.0
            prob = float(self._lib.rnnoise_process_frame(self._state, self._buf_addr, self._buf_addr))
            g0, g1 = gate.step(prob) if gate is not None else (1.0, 1.0)
            sumsq += finish_py(buf, n, g0, g1, gain, dst, start * out_ch, out_ch)
        return sumsq, prob

    def close(self) -> None:
        if self._state:
            self._lib.rnnoise_destroy(self._state)
            self._state = None

    def __del__(self) -> None:  # pragma: no cover
        try:
            self.close()
        except Exception:
            pass


def finish_py(buf, n: int, g0: float, g1: float, gain: float, out, offset: int, out_ch: int) -> float:
    """Pure-Python twin of ``airdops_finish`` (16-bit-range ``buf`` -> float ``out``)."""
    step = (g1 - g0) / (n - 1) if n > 1 else 0.0
    sumsq = 0.0
    for i in range(n):
        v = buf[i] * _INV_SCALE * (g0 + step * i) * gain
        v = 1.0 if v > 1.0 else (-1.0 if v < -1.0 else v)
        sumsq += v * v
        j = offset + i * out_ch
        for c in range(out_ch):
            out[j + c] = v
    return sumsq


def white_noise(n: int, seed: int, amplitude: float = 0.05) -> array:
    rng = random.Random(seed)
    return array("f", (rng.gauss(0.0, amplitude) for _ in range(n)))


def rms(samples: Sequence[float]) -> float:
    return math.sqrt(sum(v * v for v in samples) / len(samples)) if len(samples) else 0.0


def white_noise_check(frames: int = 100, seed: int = 1, skip: int = 10) -> tuple[float, float]:
    """Denoise white noise; returns (reduction in dB after ``skip`` warm-up frames, mean voice prob)."""
    noise = white_noise(frames * FRAME_SIZE, seed)
    d = Denoiser()
    out = array("f")
    probs = []
    try:
        for i in range(0, len(noise), FRAME_SIZE):
            o, p = d.process(noise[i : i + FRAME_SIZE])
            out.extend(o)
            probs.append(p)
    finally:
        d.close()
    reduction = 20.0 * math.log10((rms(noise) + 1e-9) / (rms(out[skip * FRAME_SIZE :]) + 1e-9))
    return reduction, sum(probs) / len(probs)


def benchmark(frames: int = 500, in_ch: int = 2, out_ch: int = 2) -> float:
    """Average microseconds the realtime path spends per 10 ms frame."""
    noise = white_noise(FRAME_SIZE * in_ch, 2)
    indata = bytearray(noise.tobytes())
    outdata = bytearray(FRAME_SIZE * out_ch * 4)
    d = Denoiser()
    try:
        d.run(indata, outdata, FRAME_SIZE, in_ch, out_ch)
        t = time.perf_counter()
        for _ in range(frames):
            d.run(indata, outdata, FRAME_SIZE, in_ch, out_ch)
        return (time.perf_counter() - t) / frames * 1e6
    finally:
        d.close()
