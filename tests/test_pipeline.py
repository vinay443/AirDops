import struct
import sys
import types

import pytest

from airdops.denoise import pipeline as pl
from airdops.denoise import rnnoise


class FakeDenoiser:
    """Halves the downmixed mic; runs the same output maths as the real thing."""

    def run(self, indata, outdata, frames, in_ch, out_ch, gate=None, gain=1.0):
        src, dst = rnnoise.float_view(indata), rnnoise.float_view(outdata)
        buf = [sum(src[i * in_ch : (i + 1) * in_ch]) / in_ch * 32767.0 * 0.5 for i in range(frames)]
        g0, g1 = gate.step(0.9) if gate is not None else (1.0, 1.0)
        return rnnoise.finish_py(buf, frames, g0, g1, gain, dst, 0, out_ch), 0.9

    def close(self):
        pass


def make_sd(fail_first=0):
    sd = types.SimpleNamespace()
    sd.opened = []
    sd.query_hostapis = lambda: [{"name": "MME"}, {"name": "Windows WASAPI"}]
    devices = [
        {"name": "Microphone Array (Intel® Smart So", "hostapi": 0, "max_input_channels": 2, "max_output_channels": 0},
        {"name": "Microphone Array (Intel® Smart Sound Technology)", "hostapi": 1, "max_input_channels": 4, "max_output_channels": 0},
        {"name": "CABLE Input (VB-Audio Virtual Cable)", "hostapi": 1, "max_input_channels": 0, "max_output_channels": 8},
    ]

    def query_devices(i=None):
        return devices if i is None else devices[i]

    sd.query_devices = query_devices

    class WasapiSettings:
        def __init__(self, auto_convert=False):
            self.auto_convert = auto_convert

    sd.WasapiSettings = WasapiSettings
    state = {"fails": fail_first}

    class Stream:
        def __init__(self, **kw):
            if state["fails"] > 0:
                state["fails"] -= 1
                raise OSError("Invalid sample rate")
            self.kw = kw
            self.active = False
            sd.opened.append(kw)

        def start(self):
            self.active = True

        def stop(self):
            self.active = False

        def close(self):
            pass

    sd.RawStream = Stream
    return sd


@pytest.fixture
def fake(monkeypatch):
    def install(fail_first=0):
        sd = make_sd(fail_first)
        monkeypatch.setitem(sys.modules, "sounddevice", sd)
        monkeypatch.setattr(pl, "Denoiser", FakeDenoiser)
        return sd

    return install


def test_maps_names_to_wasapi_devices(fake):
    sd = fake()
    assert pl.find_device(sd, "Microphone Array (Intel® Smart Sound Technology)", True) == 1
    assert pl.find_device(sd, "CABLE Input (VB-Audio Virtual Cable)", False) == 2
    assert pl.find_device(sd, "Nope", True) is None


def test_start_uses_low_latency_and_caps_channels(fake):
    sd = fake()
    p = pl.NoisePipeline("Microphone Array (Intel® Smart Sound Technology)", "CABLE Input (VB-Audio Virtual Cable)")
    p.start()
    kw = sd.opened[-1]
    assert kw["latency"] == "low" and kw["channels"] == (2, 2) and kw["blocksize"] == 480
    assert p.running
    p.stop()
    assert not p.running


def test_start_falls_back_when_driver_refuses(fake):
    sd = fake(fail_first=2)
    p = pl.NoisePipeline("Microphone Array (Intel® Smart Sound Technology)", "CABLE Input (VB-Audio Virtual Cable)")
    p.start()
    assert sd.opened[-1]["extra_settings"] is None and sd.opened[-1]["latency"] == "high"


def test_start_reports_missing_cable(fake):
    fake()
    p = pl.NoisePipeline("Microphone Array (Intel® Smart Sound Technology)", "CABLE Input (missing)")
    p.cable_name = "Nothing"
    with pytest.raises(RuntimeError):
        p.start()


def test_callback_processes_and_meters(fake):
    fake()
    p = pl.NoisePipeline("m", "c", gain_db=6)
    p._denoiser = FakeDenoiser()
    p._channels = (2, 2)
    indata = bytearray(struct.pack("<960f", *([0.2] * 960)))
    out = bytearray(480 * 2 * 4)
    p._callback(indata, out, 480, None, None)
    vals = struct.unpack("<960f", out)
    assert vals[0::2] == vals[1::2]
    assert abs(vals[0] - 0.2 * 0.5 * 10 ** (6 / 20)) < 1e-4
    assert 0.5 < p.level <= 1.0
    assert p.last_voice_prob == 0.9


def test_callback_without_denoiser_outputs_silence(fake):
    fake()
    p = pl.NoisePipeline("m", "c")
    out = bytearray(b"\x01" * 480 * 4)
    p._callback(bytearray(480 * 4), out, 480, None, None)
    assert out == bytearray(480 * 4)


def test_output_is_clipped_and_ramped():
    buf = [40000.0] * 4  # louder than full scale
    out = [0.0] * 8
    sumsq = rnnoise.finish_py(buf, 4, 0.0, 1.0, 1.0, out, 0, 2)
    assert out[0] == 0.0 and out[-1] == 1.0 and out[6] == out[7]
    assert abs(sumsq - sum(v * v for v in out[0::2])) < 1e-9
