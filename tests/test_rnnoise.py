import numpy as np
import pytest

from airdops.denoise import rnnoise

pytestmark = pytest.mark.skipif(not rnnoise.available(), reason="RNNoise library not fetched")


def _run(signal):
    d = rnnoise.Denoiser()
    out, probs = [], []
    for i in range(0, len(signal), rnnoise.FRAME_SIZE):
        o, p = d.process(signal[i : i + rnnoise.FRAME_SIZE])
        out.append(o)
        probs.append(p)
    d.close()
    return np.concatenate(out), np.array(probs)


def test_white_noise_is_suppressed():
    noise = (np.random.default_rng(0).standard_normal(48000) * 0.05).astype(np.float32)
    out, probs = _run(noise)
    reduction_db = 20 * np.log10(np.std(noise) / (np.std(out[4800:]) + 1e-12))
    assert reduction_db > 10
    assert probs.mean() < 0.5
    assert np.abs(out).max() <= 1.0


def test_partial_frame_is_handled():
    d = rnnoise.Denoiser()
    out, _ = d.process(np.zeros(100, dtype=np.float32))
    assert out.shape == (100,)
    d.close()
