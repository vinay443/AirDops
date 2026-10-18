import sys
import types

import numpy as np
import pytest

from airdops.denoise import pipeline as pl


class FakeDenoiser:
    def process(self, frame):
        return frame * 0.5, 0.9

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

    sd.Stream = Stream
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
    indata = np.full((480, 2), 0.2, dtype=np.float32)
    out = np.zeros((480, 2), dtype=np.float32)
    p._callback(indata, out, 480, None, None)
    assert np.allclose(out[:, 0], out[:, 1])
    assert abs(out[0, 0] - 0.2 * 0.5 * 10 ** (6 / 20)) < 1e-4
    assert 0.5 < p.level <= 1.0
