from airdops.audio.router import (
    CAPTURE,
    RENDER,
    STATE_ACTIVE,
    STATE_DISABLED,
    STATE_NOTPRESENT,
    STATE_UNPLUGGED,
    Endpoint,
    build_plan,
    device_label,
)

KW = ["AirPods"]
MIC = Endpoint("mic", "Microphone Array (Intel® Smart Sound Technology for Digital Microphones)", CAPTURE, STATE_ACTIVE)
SPK = Endpoint("spk", "Speakers (Realtek(R) Audio)", RENDER, STATE_ACTIVE)
CABLE_IN = Endpoint("cin", "CABLE Input (VB-Audio Virtual Cable)", RENDER, STATE_ACTIVE)
CABLE_OUT = Endpoint("cout", "CABLE Output (VB-Audio Virtual Cable)", CAPTURE, STATE_ACTIVE)


def test_split_endpoints():
    eps = [
        SPK,
        MIC,
        Endpoint("st", "Headphones (Alex's AirPods Pro Stereo)", RENDER, STATE_ACTIVE),
        Endpoint("hf", "Headset (Alex's AirPods Pro Hands-Free AG Audio)", RENDER, STATE_ACTIVE),
        Endpoint("hfm", "Headset (Alex's AirPods Pro Hands-Free AG Audio)", CAPTURE, STATE_ACTIVE),
    ]
    p = build_plan(eps, KW)
    assert p.connected and p.render_id == "st"
    assert p.device_name == "Alex's AirPods Pro"
    assert p.handsfree_render_id == "hf"
    assert sorted(p.to_disable) == ["hf", "hfm"]
    assert p.mic_id == "mic"
    assert p.cable_render_id is None


def test_unified_endpoints_with_cable():
    eps = [
        SPK,
        MIC,
        CABLE_IN,
        CABLE_OUT,
        Endpoint("u", "Headphones (AirPods Pro)", RENDER, STATE_ACTIVE),
        Endpoint("um", "Headset (AirPods Pro)", CAPTURE, STATE_DISABLED),
    ]
    p = build_plan(eps, KW)
    assert p.connected and p.render_id == "u"
    assert p.handsfree_render_id is None
    assert p.to_disable == ["um"]  # already disabled: controller skips it
    assert (p.cable_render_id, p.cable_capture_id) == ("cin", "cout")
    assert p.mic_id == "mic"  # never the cable or the AirPods


def test_disconnected():
    eps = [
        SPK,
        MIC,
        Endpoint("u", "Headphones (AirPods Pro)", RENDER, STATE_UNPLUGGED),
        Endpoint("um", "Headset (AirPods Pro)", CAPTURE, STATE_DISABLED),
        Endpoint("old", "Headset (Old AirPods)", CAPTURE, STATE_NOTPRESENT),
    ]
    p = build_plan(eps, KW)
    assert not p.connected and p.render_id is None
    assert p.airpods_capture_ids == ["um"]


def test_preferred_and_previous_mic():
    usb = Endpoint("usb", "Microphone (Blue Yeti)", CAPTURE, STATE_ACTIVE)
    eps = [MIC, usb]
    assert build_plan(eps, KW, preferred_mic="yeti").mic_id == "usb"
    assert build_plan(eps, KW, previous_default_mic="usb").mic_id == "usb"
    assert build_plan(eps, KW).mic_id == "mic"


def test_only_headset_named_render_is_still_used():
    eps = [Endpoint("h", "Headset (AirPods)", RENDER, STATE_ACTIVE)]
    p = build_plan(eps, KW)
    assert p.connected and p.render_id == "h"
    assert p.to_disable == []  # never disable the only output


def test_device_label():
    assert device_label("Headphones (AirPods Pro Stereo)") == "AirPods Pro"
    assert device_label("Headset (AirPods Pro Hands-Free AG Audio)") == "AirPods Pro"
    assert device_label("AirPods") == "AirPods"
