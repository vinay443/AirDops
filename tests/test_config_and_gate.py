from airdops.config import Settings, State
from airdops.denoise.gate import VoiceGate


def test_settings_validation():
    s = Settings.from_dict(
        {
            "mode": "weird",
            "noise_suppression": "yes",  # wrong type -> default kept
            "low_battery_percent": 1,
            "mic_gain_db": 6,  # int accepted as float
            "device_keywords": ["", 5, "Beats"],
            "unknown": 1,
            "auto_pause": 1,  # int is not bool -> default kept
        }
    )
    assert s.mode == "game"
    assert s.noise_suppression is True
    assert s.low_battery_percent == 5
    assert s.mic_gain_db == 6.0
    assert s.device_keywords == ["Beats"]
    assert s.auto_pause is True


def test_state_validation():
    st = State.from_dict({"disabled_endpoints": ["a", 3], "saved_defaults": {"capture": "x", "bad": 1}, "ducking_original": True})
    assert st.disabled_endpoints == ["a"]
    assert st.saved_defaults == {"capture": "x"}
    assert st.ducking_original is None


def test_voice_gate_opens_holds_and_closes():
    g = VoiceGate(hold_ms=50, release_ms=10, attack_ms=1)
    frame = [1.0] * 480
    quiet = g.apply(frame, 0.0)
    assert max(quiet) < 0.05
    for _ in range(5):
        loud = g.apply(frame, 0.9)
    assert loud[-1] > 0.95
    for _ in range(3):  # within hold time: stays open
        held = g.apply(frame, 0.1)
    assert held[-1] > 0.9
    for _ in range(30):
        closed = g.apply(frame, 0.1)
    assert closed[-1] < 0.05


def test_voice_gate_step_ramps_from_previous_gain():
    g = VoiceGate(attack_ms=1)
    g0, g1 = g.step(0.9)
    assert g0 == g.floor and g1 > 0.9
    g0b, _ = g.step(0.9)
    assert g0b == g1
