"""Regression tests ported from tests/fn.test.js.

Fixtures are real captured packets (hex) — keep them as ground truth.
"""
from types import SimpleNamespace

from cam_reverse.crypto import xq_bytes_dec, xq_bytes_enc
from cam_reverse.dataview import DV
from cam_reverse.handlers import parse_dev_status_ack, parse_list_wifi
from cam_reverse.impl import (
    SendDevStatus,
    SendStartVideo,
    SendUsrChk,
    SendWifiDetails,
    parse_PunchPkt,
)
from cam_reverse.session import make_p2p_rdy

SIMPLE_ENC = bytes([1] * 31 + [0])
SIMPLE_DEC = bytes([0, 0, 0, 1] + [0] * 28)


def _hb(hs):
    return bytes.fromhex(hs)


def _sess(cmd_id=0, ticket=(0, 0, 0, 0)):
    return SimpleNamespace(outgoing_command_id=cmd_id, ticket=list(ticket))


# -- crypto ----------------------------------------------------------------
def test_encrypt_without_rotation():
    dv = DV(bytearray([1, 2, 3, 4]))
    xq_bytes_enc(dv, dv.byte_length, 0)
    assert [dv.add(i).read_u8() for i in range(4)] == [0, 3, 2, 5]


def test_decrypt_without_rotation():
    dv = DV(bytearray([1, 2, 3, 4]))
    xq_bytes_dec(dv, dv.byte_length, 0)
    assert [dv.add(i).read_u8() for i in range(4)] == [0, 3, 2, 5]


def test_decrypts_simple_input():
    dv = DV(bytearray(SIMPLE_ENC))
    xq_bytes_dec(dv, len(SIMPLE_ENC), 4)
    assert bytes(dv.buf) == SIMPLE_DEC


def test_encrypts_simple_input():
    dv = DV(bytearray(SIMPLE_DEC))
    xq_bytes_enc(dv, len(SIMPLE_DEC), 4)
    assert bytes(dv.buf) == SIMPLE_ENC


def test_enc_dec_roundtrip():
    original = bytes(range(0, 240, 3))
    dv = DV(bytearray(original))
    xq_bytes_enc(dv, len(original), 4)
    assert bytes(dv.buf) != original
    xq_bytes_dec(dv, len(original), 4)
    assert bytes(dv.buf) == original


# -- parse -----------------------------------------------------------------
def test_parses_punch_pkt():
    pkt = DV(_hb("f14100144241544400000000000262ca574f4e4a4d000000"))
    dev = parse_PunchPkt(pkt)
    assert (dev.prefix, dev.serial, dev.suffix, dev.serial_u64, dev.dev_id) == (
        "BATD",
        "156362",
        "WONJM",
        156362,
        "BATD156362WONJM",
    )


def test_parses_punch_pkt_3_letter_prefix():
    pkt = DV(_hb("f14100145848410000000000000003e24b4d4d4542000000"))
    dev = parse_PunchPkt(pkt)
    assert (dev.prefix, dev.serial, dev.suffix, dev.dev_id) == (
        "XHA",
        "994",
        "KMMEB",
        "XHA994KMMEB",
    )


def test_replies_to_punch_pkt_3_letter_prefix():
    in_pkt_str = "f14100145848410000000000000003e24b4d4d4542000000"
    dev = parse_PunchPkt(DV(_hb(in_pkt_str)))
    p2prdy = make_p2p_rdy(dev).to_bytes().hex()
    assert in_pkt_str[8:] == p2prdy[8:]


def test_parses_wifiscan_chan0():
    in_pkt_str = (
        "f1d00238d1000009110a03612c020100060000002f4f44550101010101010101010101010101010101010101010101010101010101010101010101010101010101010101010101010101010101010101a741a15822a1010101010101b2fefefe650101010101010101010101"
        "404253422f4674647275010101010101010101010101010101010101010101010101010101010101010101010101010101010101010101010101010101010101ab41a158605c010101010101b6fefefe650101010101010101010101"
        "404253422f4f44550101010101010101010101010101010101010101010101010101010101010101010101010101010101010101010101010101010101010101a741a158605c010101010101c3fefefe650101010101010101010101"
        "404253422f4674647275010101010101010101010101010101010101010101010101010101010101010101010101010101010101010101010101010101010101af41a15822a1010101010101c8fefefe650101010101010101010101"
        "404253422f4f44550101010101010101010101010101010101010101010101010101010101010101010101010101010101010101010101010101010101010101933aac0b5330010101010101b4fefefe650101010101010101010101"
        "404253422f4674647275010101010101010101010101010101010101010101010101010101010101010101010101010101010101010101010101010101010101973aac0b5330010101010101b4fefefe650101010101010101010101"
        "40425342"
    )
    pkt = DV(_hb(in_pkt_str))
    payload_len = pkt.add(0xC).read_u16le()
    xq_bytes_dec(pkt.add(20), payload_len - 4, 4)
    items = [i.__dict__ for i in parse_list_wifi(pkt)]
    assert items == [
        {"channel": 0, "dbm0": 4294967219, "dbm1": 100, "mac": "a6:40:a0:59:23:a0", "mode": 0, "security": 0, "ssid": "ACRC.NET"},
        {"channel": 0, "dbm0": 4294967223, "dbm1": 100, "mac": "aa:40:a0:59:61:5d", "mode": 0, "security": 0, "ssid": "ACRC.Guest"},
        {"channel": 0, "dbm0": 4294967234, "dbm1": 100, "mac": "a6:40:a0:59:61:5d", "mode": 0, "security": 0, "ssid": "ACRC.NET"},
        {"channel": 0, "dbm0": 4294967241, "dbm1": 100, "mac": "ae:40:a0:59:23:a0", "mode": 0, "security": 0, "ssid": "ACRC.Guest"},
        {"channel": 0, "dbm0": 4294967221, "dbm1": 100, "mac": "92:3b:ad:0a:52:31", "mode": 0, "security": 0, "ssid": "ACRC.NET"},
        {"channel": 0, "dbm0": 4294967221, "dbm1": 100, "mac": "96:3b:ad:0a:52:31", "mode": 0, "security": 0, "ssid": "ACRC.Guest"},
    ]


def test_parses_devstatusack():
    pkt = DV(
        _hb(
            "f1d0008cd1000009110a08118000000000000000190e010101010101fefefefebefefefe01000001010101010101010101010101010101010101010101010101010101010101010101010101010101010101010101010101010101010101010101010101010101010100010101010001030101010101010101010101010101fefefefefe010101010101010134030300"
        )
    )
    payload_len = pkt.add(0xC).read_u16le()
    xq_bytes_dec(pkt.add(20), payload_len - 4, 0)
    got = parse_dev_status_ack(pkt)
    assert (got.battery_mV, got.charging, got.dbm, got.swver) == (0, False, -256, "0.0.15.24")


# -- build -----------------------------------------------------------------
def test_builds_send_usr_chk():
    expected = (
        "f1d000b0d1000000110a2010a400ff00000000006f01010101010101010101010101010101010101010101010101010160656c686f01010101010101010101010101010101010101010101010101010101010101010101010101010101010101010101010101010101010101010101010101010101010101010101010101010101010101010101010101010101010101010101010101010101010101010101010101010101010101010101010101010160656c68"
    )
    got = SendUsrChk(_sess(0, (0, 0, 0, 0)), "admin", "admin")
    assert got.to_bytes().hex() == expected


def test_builds_send_start_video():
    got = SendStartVideo(_sess(0, (1, 2, 3, 4)))
    assert got.to_bytes().hex() == "f1d00010d1000000110a10300400000001020304"


def test_builds_send_dev_status():
    got = SendDevStatus(_sess(0, (1, 2, 3, 4)))
    assert got.to_bytes().hex() == "f1d00010d1000000110a08100400000001020304"


def test_builds_wifi_settings_set():
    expected = (
        "f1d00118d1000002110a01600c01000001020304"
        "0101010101010101010101010101010100010101"
        "726a786f64750101010101010101010101010101010101010101010101010101"
        "7274716473627360710101010101010101010101010101010101010101010101010101010101010101010101010101010101010101010101010101010101010101010101010101010101010101010101010101010101010101010101010101010101010101010101010101010101010101010101010101010101010101010101"
        "312f312f312f31010101010101010101"
        "312f3334342f3334342f333434010101"
        "312f312f312f31010101010101010101"
        "312f312f312f31010101010101010101"
        "312f312f312f31010101010101010101"
        "01010101"
    )
    got = SendWifiDetails(_sess(2, (1, 2, 3, 4)), "skynet", "supercrap", 0, True)
    assert got.to_bytes().hex() == expected


def test_builds_wifi_settings_set_with_channel():
    expected = "f1d00118d100000c110a01600c010000303574720101010101010101030101010101010100010101404253422f4f445501010101010101010101010101010101010101010101010167606a6471607272010101010101010101010101010101010101010101010101010101010101010101010101010101010101010101010101010101010101010101010101010101010101010101010101010101010101010101010101010101010101010101010101010101010101010101010101010101010101010101010101312f312f312f31010101010101010101312f3334342f3334342f333434010101312f312f312f31010101010101010101312f312f312f31010101010101010101312f312f312f3101010101010101010101010101"
    got = SendWifiDetails(_sess(0xC, (0x30, 0x35, 0x74, 0x72)), "ACRC.NET", "fakepass", 2, True)
    assert got.to_bytes().hex() == expected
