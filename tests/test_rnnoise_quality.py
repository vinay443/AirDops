"""The from-source RNNoise build must sound like the old prebuilt one.

Runs only when ``AIRDOPS_RNNOISE_REFERENCE`` points at the old library
(``python scripts/fetch_rnnoise.py`` prints the path); CI sets it.

The test signal is synthetic, so the absolute numbers mean little. What
matters is that the new 8-bit build and the old full-precision build remove
about as much noise, keep about as much "voice", and agree on voice activity.
Metrics are written to build/rnnoise-quality.txt for the CI summary.
"""

from __future__ import annotations

import math
import os
import random
from array import array
from pathlib import Path

import pytest

from airdops.denoise import rnnoise

REFERENCE = os.environ.get("AIRDOPS_RNNOISE_REFERENCE", "")
pytestmark = pytest.mark.skipif(
    not (REFERENCE and Path(REFERENCE).is_file() and rnnoise.available()),
    reason="set AIRDOPS_RNNOISE_REFERENCE to the old RNNoise library to compare",
)

SR = rnnoise.SAMPLE_RATE
N = rnnoise.FRAME_SIZE
SECONDS = 4


def _signals() -> tuple[array, array, list[bool]]:
    """(clean voice-like signal, voice + noise, per-frame 'voice active' flags)."""
    rng = random.Random(7)
    total = SR * SECONDS
    clean = array("f", bytes(4 * total))
    phase = 0.0
    formants = ((700.0, 130.0), (1220.0, 170.0), (2600.0, 250.0))
    for i in range(total):
        t = i / SR
        syllable = (t % 1.0) < 0.6  # 0.6 s "talking", 0.4 s pause, every second
        if not syllable:
            continue
        f0 = 120.0 + 30.0 * math.sin(2 * math.pi * 0.7 * t)
        phase += 2 * math.pi * f0 / SR
        env = math.sin(math.pi * (t % 1.0) / 0.6) ** 0.5
        v = 0.0
        for h in range(1, 20):
            f = h * f0
            amp = sum(math.exp(-((f - fc) / bw) ** 2) for fc, bw in formants) + 0.05
            v += amp / h**0.5 * math.sin(h * phase)
        clean[i] = 0.08 * env * v
    noisy = array("f", clean)
    b = [0.0, 0.0, 0.0]
    for i in range(total):  # pink-ish noise (cheap 3-pole filter) plus keyboard clicks
        w = rng.gauss(0.0, 1.0)
        b[0] = 0.99765 * b[0] + w * 0.0990460
        b[1] = 0.96300 * b[1] + w * 0.2965164
        b[2] = 0.57000 * b[2] + w * 1.0526913
        n = 0.012 * (b[0] + b[1] + b[2] + w * 0.1848)
        if i % 9000 < 40:
            n += 0.25 * rng.uniform(-1, 1) * math.exp(-(i % 9000) / 8)
        noisy[i] += n
    active = [((f * N) / SR) % 1.0 < 0.6 for f in range(total // N)]
    return clean, noisy, active


def _run(library: str | None, noisy: array) -> tuple[array, list[float]]:
    d = rnnoise.Denoiser(library)
    out = array("f")
    probs = []
    try:
        for i in range(0, len(noisy), N):
            o, p = d.process(noisy[i : i + N])
            out.extend(o)
            probs.append(p)
    finally:
        d.close()
    return out, probs


def _energy(sig, frames) -> float:
    return sum(sig[f * N + k] ** 2 for f in frames for k in range(N)) + 1e-12


def _db(x: float) -> float:
    return 10 * math.log10(x)


def test_new_build_matches_reference():
    clean, noisy, active = _signals()
    warm = 50  # skip the first half second while the network settles
    speech = [f for f, a in enumerate(active) if a and f >= warm]
    pauses = [f for f, a in enumerate(active) if not a and f >= warm]
    results = {}
    for label, lib in (("new", None), ("reference", REFERENCE)):
        out, probs = _run(lib, noisy)
        results[label] = {
            "out": out,
            "probs": probs,
            "noise_reduction_db": _db(_energy(noisy, pauses) / _energy(out, pauses)),
            "voice_kept_db": _db(_energy(out, speech) / _energy(clean, speech)),
            "vad_speech": sum(probs[f] for f in speech) / len(speech),
            "vad_pause": sum(probs[f] for f in pauses) / len(pauses),
        }
    new, ref = results["new"], results["reference"]
    diff = sum((a - b) ** 2 for a, b in zip(new["out"], ref["out"])) + 1e-12
    agreement_db = _db(sum(b * b for b in ref["out"]) / diff)
    vad_diff = sum(abs(a - b) for a, b in zip(new["probs"], ref["probs"])) / len(ref["probs"])

    new_lib = rnnoise.library_path()
    lines = [
        f"library size: new {new_lib.stat().st_size / 1024:.0f} KiB, reference {Path(REFERENCE).stat().st_size / 1024:.0f} KiB",
    ]
    for label in ("new", "reference"):
        r = results[label]
        lines.append(
            f"{label}: noise removed {r['noise_reduction_db']:.1f} dB, voice level {r['voice_kept_db']:+.1f} dB, "
            f"VAD speech {r['vad_speech']:.2f} / pauses {r['vad_pause']:.2f}"
        )
    lines.append(f"agreement new vs reference: {agreement_db:.1f} dB, mean VAD difference {vad_diff:.3f}")
    report = "\n".join(lines)
    out_dir = Path(__file__).resolve().parent.parent / "build"
    out_dir.mkdir(exist_ok=True)
    (out_dir / "rnnoise-quality.txt").write_text(report + "\n", encoding="utf-8")
    print(report)

    assert new["noise_reduction_db"] >= ref["noise_reduction_db"] - 3.0, report
    assert abs(new["voice_kept_db"] - ref["voice_kept_db"]) <= 2.0, report
    assert vad_diff <= 0.15, report
