import struct

import pytest

from airdops.denoise import rnnoise

pytestmark = pytest.mark.skipif(not rnnoise.available(), reason="RNNoise library not built")


def test_white_noise_is_suppressed():
    reduction_db, mean_prob = rnnoise.white_noise_check(frames=100, seed=0)
    assert reduction_db > 10
    assert mean_prob < 0.5


def test_output_stays_in_range():
    d = rnnoise.Denoiser()
    noise = rnnoise.white_noise(4800, 3, amplitude=0.5)
    for i in range(0, len(noise), rnnoise.FRAME_SIZE):
        out, _ = d.process(noise[i : i + rnnoise.FRAME_SIZE])
        assert max(abs(v) for v in out) <= 1.0
    d.close()


def test_partial_frame_is_handled():
    d = rnnoise.Denoiser()
    out, _ = d.process([0.0] * 100)
    assert len(out) == 100
    d.close()


@pytest.mark.skipif(not rnnoise.has_native_helper(), reason="library built without the AirDops helper")
def test_native_frame_maths_match_python():
    """airdops_denoise (pass-through mode) and airdops_finish against their Python twins."""
    lib = rnnoise.load()
    stereo = rnnoise.white_noise(480 * 2, 5, amplitude=0.3)
    indata = bytearray(stereo.tobytes())
    buf = rnnoise.array("f", [0.0] * 480)
    prob = lib.airdops_denoise(None, rnnoise.address(indata), 2, 480, rnnoise.address(buf))
    assert prob == 1.0
    want = [(stereo[2 * i] + stereo[2 * i + 1]) / 2 * 32767.0 for i in range(480)]
    assert max(abs(a - b) for a, b in zip(buf, want)) < 1e-2  # float32 vs double, 16-bit scale

    for g0, g1, gain in ((0.01, 1.0, 1.0), (1.0, 1.0, 4.0), (0.5, 0.2, 2.0)):
        out_c = bytearray(480 * 2 * 4)
        out_py = [0.0] * 960
        s_c = lib.airdops_finish(rnnoise.address(buf), 480, g0, g1, gain, rnnoise.address(out_c), 2)
        s_py = rnnoise.finish_py(buf, 480, g0, g1, gain, out_py, 0, 2)
        c_vals = struct.unpack("<960f", out_c)
        assert max(abs(a - b) for a, b in zip(c_vals, out_py)) < 1e-5
        assert abs(s_c - s_py) < 1e-3 * max(1.0, s_py)
        assert max(abs(v) for v in c_vals) <= 1.0


def test_realtime_path_matches_process():
    """run() (native or fallback) gives the same audio as the simple process() path."""
    mono = rnnoise.white_noise(480 * 10, 6, amplitude=0.2)
    a, b = rnnoise.Denoiser(), rnnoise.Denoiser()
    for f in range(10):
        frame = mono[f * 480 : (f + 1) * 480]
        want, p_want = a.process(frame)
        indata = bytearray(frame.tobytes())
        out = bytearray(480 * 4)
        _, p_got = b.run(indata, out, 480, 1, 1)
        got = struct.unpack("<480f", out)
        assert abs(p_got - p_want) < 1e-3
        assert max(abs(x - y) for x, y in zip(got, want)) < 1e-3
    a.close()
    b.close()


def test_benchmark_runs():
    assert 0 < rnnoise.benchmark(20) < 10_000  # well under the 10 ms budget
