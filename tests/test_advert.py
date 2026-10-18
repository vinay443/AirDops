from airdops.ble.advert import family, parse_proximity


def packet(model=0x1420, status=0x2B, batt=0x98, flags_case=0x15):
    return bytes([0x07, 0x19, 0x01, model >> 8, model & 0xFF, status, batt, flags_case, 0x05, 0x00] + [0] * 16)


def test_left_broadcasting():
    s = parse_proximity(packet())
    assert s is not None
    assert s.model_name == "AirPods Pro 2"
    assert (s.left_battery, s.right_battery, s.case_battery) == (80, 90, 50)
    assert s.left_charging and not s.right_charging and not s.case_charging
    assert s.left_in_ear and s.right_in_ear
    assert s.lowest_bud_battery == 80
    assert s.buds_in_ear == 2


def test_right_broadcasting_flips_sides():
    s = parse_proximity(packet(status=0x03, flags_case=0x25))
    assert (s.left_battery, s.right_battery) == (90, 80)
    # 0x2 flag = "other bud" charging -> left when the right bud broadcasts
    assert s.left_charging and not s.right_charging
    assert s.right_in_ear and not s.left_in_ear


def test_case_charging_and_unknown_battery():
    s = parse_proximity(packet(batt=0xF7, flags_case=0x4F))
    assert s.left_battery == 70
    assert s.right_battery is None
    assert s.case_battery is None
    assert s.case_charging


def test_single_unit_headphones():
    s = parse_proximity(packet(model=0x0A20, status=0x22, batt=0xF6, flags_case=0x0F))
    assert s.single_unit
    assert s.left_battery == s.right_battery == 60
    assert s.case_battery is None


def test_unknown_model_still_parses():
    s = parse_proximity(packet(model=0x9999))
    assert s is not None and "0x9999" in s.model_name


def test_rejects_other_messages():
    assert parse_proximity(b"") is None
    assert parse_proximity(bytes([0x10, 0x05, 0x01, 0x18, 0x00, 0x00])) is None  # "nearby" message
    assert parse_proximity(bytes([0x07, 0x19, 0x01])) is None  # truncated


def test_family():
    assert family("Headphones (AirPods Pro Stereo)") == "pro"
    assert family("AirPods Pro 2 (USB-C)") == "pro"
    assert family("AirPods Max") == "max"
    assert family("AirPods 4 (ANC)") == "airpods"
