from dataclasses import replace

from airdops.audio.router import CAPTURE, RENDER, STATE_ACTIVE, STATE_DISABLED, STATE_UNPLUGGED, Endpoint
from airdops.config import Settings, State
from airdops.controller import Controller


class FakeAudio:
    def __init__(self, endpoints):
        self.eps = {e.id: e for e in endpoints}
        self.defaults = {}  # (flow, role) -> id
        self.refuse_disable = False

    def list_endpoints(self):
        return list(self.eps.values())

    def get_default(self, flow, role):
        return self.defaults.get((flow, role))

    def set_default(self, eid, roles):
        flow = self.eps[eid].flow
        for r in roles:
            self.defaults[(flow, r)] = eid
        return True

    def set_enabled(self, eid, enabled):
        if self.refuse_disable and not enabled:
            return False
        self.eps[eid] = replace(self.eps[eid], state=STATE_ACTIVE if enabled else STATE_DISABLED)
        return True

    def plug(self, connected):
        for eid in ("st", "hf"):
            self.eps[eid] = replace(self.eps[eid], state=STATE_ACTIVE if connected else STATE_UNPLUGGED)
        e = self.eps["hfm"]
        if e.state != STATE_DISABLED:
            self.eps["hfm"] = replace(e, state=STATE_ACTIVE if connected else STATE_UNPLUGGED)


class FakeDucking:
    def __init__(self):
        self.value = None

    def read(self):
        return (self.value is not None, self.value)

    def write(self, value):
        self.value = value
        return True


class FakePipeline:
    instances = []

    def __init__(self, mic, cable, gate, gain):
        self.mic_name = mic
        self.running = False
        FakePipeline.instances.append(self)

    def start(self):
        self.running = True

    def stop(self):
        self.running = False

    def set_voice_gate(self, enabled):
        pass

    def set_gain_db(self, gain):
        pass


def make(with_cable=False, ns=True):
    eps = [
        Endpoint("spk", "Speakers (Realtek(R) Audio)", RENDER, STATE_ACTIVE),
        Endpoint("mic", "Microphone Array (Realtek(R) Audio)", CAPTURE, STATE_ACTIVE),
        Endpoint("st", "Headphones (AirPods Pro Stereo)", RENDER, STATE_UNPLUGGED),
        Endpoint("hf", "Headset (AirPods Pro Hands-Free AG Audio)", RENDER, STATE_UNPLUGGED),
        Endpoint("hfm", "Headset (AirPods Pro Hands-Free AG Audio)", CAPTURE, STATE_UNPLUGGED),
    ]
    if with_cable:
        eps += [
            Endpoint("cin", "CABLE Input (VB-Audio Virtual Cable)", RENDER, STATE_ACTIVE),
            Endpoint("cout", "CABLE Output (VB-Audio Virtual Cable)", CAPTURE, STATE_ACTIVE),
        ]
    audio = FakeAudio(eps)
    audio.defaults = {(RENDER, r): "spk" for r in range(3)} | {(CAPTURE, r): "mic" for r in range(3)}
    duck = FakeDucking()
    notes = []
    saved = []
    c = Controller(
        Settings(noise_suppression=ns),
        State(),
        audio,
        duck,
        FakePipeline,
        lambda s: saved.append(1),
        notify=lambda t, m: notes.append(t),
    )
    return c, audio, duck, notes


def test_game_mode_lifecycle_without_cable():
    c, audio, duck, notes = make()
    st = c.tick()
    assert not st.connected
    assert c.state.saved_defaults["capture"] == "mic"

    audio.plug(True)
    # Windows itself makes the AirPods the default when they connect.
    audio.defaults.update({(RENDER, r): "hf" for r in range(3)} | {(CAPTURE, r): "hfm" for r in range(3)})
    st = c.tick()
    assert st.connected and st.hfp_blocked
    assert audio.eps["hfm"].state == STATE_DISABLED
    assert audio.eps["hf"].state == STATE_DISABLED
    assert all(audio.defaults[(RENDER, r)] == "st" for r in range(3))
    assert all(audio.defaults[(CAPTURE, r)] == "mic" for r in range(3))
    assert duck.value == 3 and c.state.ducking_changed
    assert "Noise suppression needs VB-Cable" in notes

    audio.plug(False)
    st = c.tick()
    assert not st.connected
    assert duck.value is None and not c.state.ducking_changed  # original (absent) restored
    assert audio.eps["hfm"].state == STATE_DISABLED  # stays blocked while AirDops runs

    c.restore_all()
    assert audio.eps["hfm"].state != STATE_DISABLED
    assert audio.eps["hf"].state != STATE_DISABLED
    assert c.state.disabled_endpoints == []


def test_noise_suppression_routes_through_cable():
    FakePipeline.instances.clear()
    c, audio, duck, notes = make(with_cable=True)
    c.tick()
    audio.plug(True)
    st = c.tick()
    assert st.noise_suppression_active
    assert FakePipeline.instances[-1].running
    assert FakePipeline.instances[-1].mic_name == "Microphone Array (Realtek(R) Audio)"
    assert all(audio.defaults[(CAPTURE, r)] == "cout" for r in range(3))

    audio.plug(False)
    c.tick()
    assert not FakePipeline.instances[-1].running
    assert all(audio.defaults[(CAPTURE, r)] == "mic" for r in range(3))  # back to normal


def test_call_mode_reenables_and_uses_airpods_mic():
    c, audio, duck, notes = make()
    c.tick()
    audio.plug(True)
    c.tick()
    c.set_mode("call")
    c.tick()  # re-enables the AirPods endpoints
    c.tick()  # then picks them as defaults
    assert audio.eps["hfm"].state == STATE_ACTIVE
    assert audio.defaults[(CAPTURE, 0)] == "hfm"
    assert audio.defaults[(RENDER, 0)] == "st"
    assert audio.defaults[(RENDER, 2)] == "hf"
    assert duck.value is None
    c.set_mode("game")
    c.tick()
    assert audio.eps["hfm"].state == STATE_DISABLED


def test_user_disabled_endpoint_is_not_reenabled():
    c, audio, duck, notes = make()
    audio.eps["hfm"] = replace(audio.eps["hfm"], state=STATE_DISABLED)  # user did this
    c.tick()
    audio.plug(True)
    c.tick()
    c.restore_all()
    assert audio.eps["hfm"].state == STATE_DISABLED
    assert audio.eps["hf"].state == STATE_ACTIVE


def test_disable_refused_warns_once():
    c, audio, duck, notes = make()
    audio.refuse_disable = True
    audio.plug(True)
    st = c.tick()
    c.tick()
    assert not st.hfp_blocked
    assert notes.count("Couldn't fully block the AirPods mic") == 1


def test_existing_ducking_preference_restored():
    c, audio, duck, notes = make()
    duck.value = 2
    audio.plug(True)
    c.tick()
    assert duck.value == 3
    c.restore_all()
    assert duck.value == 2


def test_first_run_with_airpods_already_connected_restores_a_real_mic():
    FakePipeline.instances.clear()
    c, audio, duck, notes = make(with_cable=True)
    audio.plug(True)
    audio.defaults.update({(CAPTURE, r): "hfm" for r in range(3)})  # Windows picked the AirPods mic
    c.tick()
    assert audio.defaults[(CAPTURE, 0)] == "cout"
    audio.plug(False)
    c.tick()
    assert all(audio.defaults[(CAPTURE, r)] == "mic" for r in range(3))  # not left on the silent cable
