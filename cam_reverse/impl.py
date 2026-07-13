"""Outgoing packet builders + PunchPkt parser. Port of ``impl.ts``."""
from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional

from .crypto import xq_bytes_enc
from .datatypes import Commands, ControlCommands, ccDest
from .dataview import DV
from .utils import u16_swap


def _str2byte(s: str) -> bytes:
    return s.encode("latin-1")


def make_data_read_write(session, command: int, data: Optional[DV]) -> DV:
    DRW_HEADER_LEN = 0x10
    TOKEN_LEN = 0x4
    CHANNEL = 0
    START_CMD = 0x110A

    pkt_len = DRW_HEADER_LEN + TOKEN_LEN
    payload_len = TOKEN_LEN
    buf_copy: Optional[bytearray] = None
    if data is not None and data.byte_length > 4:
        buf_copy = bytearray(data.buf[data.offset :])
        buf_dv = DV(buf_copy)
        # mutates buf_copy in place; must not touch the caller's buffer
        xq_bytes_enc(buf_dv, buf_dv.byte_length, 4)
        pkt_len += buf_dv.byte_length
        payload_len += buf_dv.byte_length

    ret = DV.alloc(pkt_len)
    ret.add(0).write_u16(Commands["Drw"])
    ret.add(2).write_u16(pkt_len - 4)  # -4: ignore [0xf1, 0xd0, len, len]
    ret.add(4).write_u8(0xD1)
    ret.add(5).write_u8(CHANNEL)
    ret.add(6).write_u16(session.outgoing_command_id)
    ret.add(8).write_u16(START_CMD)
    ret.add(10).write_u16(command)
    ret.add(12).write_u16(u16_swap(payload_len))
    ret.add(14).write_u16(ccDest.get(command, 0))
    ret.add(16).write_byte_array(session.ticket)
    if buf_copy is not None:
        ret.add(20).write_byte_array(buf_copy)

    session.outgoing_command_id += 1
    return ret


def SendIRToggle(session) -> DV:
    return make_data_read_write(session, ControlCommands["IRToggle"], None)


def SendDevStatus(session) -> DV:
    return make_data_read_write(session, ControlCommands["DevStatus"], None)


def SendWifiSettings(session) -> DV:
    return make_data_read_write(session, ControlCommands["WifiSettings"], None)


def SendListWifi(session) -> DV:
    return make_data_read_write(session, ControlCommands["ListWifi"], None)


def SendStopVideo(session) -> DV:
    return make_data_read_write(session, ControlCommands["StopVideo"], None)


def SendStartVideo(session) -> DV:
    return make_data_read_write(session, ControlCommands["StartVideo"], None)


def SendVideoResolution(session, resol: int) -> List[DV]:
    # 0x1 = resolution, specified by ID not by size.
    pairs = {
        1: [[0x1, 0x0, 0x0, 0x0, 0x0, 0x0, 0x0, 0x0]],  # 320x240
        2: [[0x1, 0x0, 0x0, 0x0, 0x2, 0x0, 0x0, 0x0]],  # 640x480
        3: [[0x1, 0x0, 0x0, 0x0, 0x3, 0x0, 0x0, 0x0]],
        4: [[0x1, 0x0, 0x0, 0x0, 0x4, 0x0, 0x0, 0x0]],
    }
    out = []
    for payload in pairs[resol]:
        dv = DV(bytearray(payload))
        out.append(make_data_read_write(session, ControlCommands["VideoParamSet"], dv))
    return out


def SendReboot(session) -> DV:
    return make_data_read_write(session, ControlCommands["Reboot"], None)


def SendWifiDetails(session, ssid: str, password: str, channel: int, dhcp: bool) -> DV:
    if not dhcp:
        raise ValueError("only DHCP is supported")
    cmd_payload = DV.alloc(0x108)
    mask_reversed = "0.255.255.255"
    m_ip = "0.0.0.0"
    m_gw = "0.0.0.0"
    m_dns1 = "0.0.0.0"
    m_dns2 = "0.0.0.0"

    # tag_wifiParams in types/all.h
    cmd_payload.add(0x0C).write_u8(channel)
    cmd_payload.add(0x10).write_u8(0)  # TODO: AUTH
    cmd_payload.add(0x14).write_u8(1)  # DHCP
    cmd_payload.add(0x18).write_byte_array(_str2byte(ssid))
    cmd_payload.add(0x38).write_byte_array(_str2byte(password))
    cmd_payload.add(0xB8).write_byte_array(_str2byte(m_ip))
    cmd_payload.add(0xC8).write_byte_array(_str2byte(mask_reversed))
    cmd_payload.add(0xD8).write_byte_array(_str2byte(m_gw))
    cmd_payload.add(0xE8).write_byte_array(_str2byte(m_dns1))
    cmd_payload.add(0xF8).write_byte_array(_str2byte(m_dns2))

    return make_data_read_write(session, ControlCommands["WifiSettingsSet"], cmd_payload)


def SendUsrChk(session, username: str, password: str) -> DV:
    # char account[0x20]; char password[0x80];
    cmd_payload = DV.alloc(0x20 + 0x80)
    cmd_payload.write_byte_array(_str2byte(username))
    cmd_payload.add(0x20).write_byte_array(_str2byte(password))
    return make_data_read_write(session, ControlCommands["ConnectUser"], cmd_payload)


def create_LanSearchExt() -> DV:
    outbuf = DV.alloc(4)
    outbuf.write_u16(Commands["LanSearchExt"])
    outbuf.add(2).write_u16(0x0)
    return outbuf


def create_LanSearch() -> DV:
    outbuf = DV.alloc(4)
    outbuf.write_u16(Commands["LanSearch"])
    outbuf.add(2).write_u16(0x0)
    return outbuf


def create_P2pRdy(inbuf: DV) -> DV:
    P2PRDY_SIZE = 0x14
    outbuf = DV.alloc(P2PRDY_SIZE + 4)
    outbuf.write_u16(Commands["P2pRdy"])
    outbuf.add(2).write_u16(P2PRDY_SIZE)
    outbuf.add(4).write_byte_array(inbuf.read_byte_array(P2PRDY_SIZE))
    return outbuf


def create_P2pAlive() -> DV:
    outbuf = DV.alloc(4)
    outbuf.write_u16(Commands["P2PAlive"])
    outbuf.add(2).write_u16(0)
    return outbuf


def create_P2pClose() -> DV:
    outbuf = DV.alloc(4)
    outbuf.write_u16(Commands["Close"])
    outbuf.add(2).write_u16(0)
    return outbuf


@dataclass
class DevSerial:
    prefix: str
    serial: str
    suffix: str
    serial_u64: int
    dev_id: str


def parse_PunchPkt(dv: DV) -> DevSerial:
    dv.read_u16()  # punch command
    length = dv.add(2).read_u16()
    prefix = dv.add(4).read_string(4)
    serial_u64 = dv.add(8).read_u64()
    serial = str(serial_u64)
    suffix = dv.add(16).read_string(length - 16 + 4)  # 16 = offset, +4 header
    dev_id = prefix + serial + suffix
    return DevSerial(prefix, serial, suffix, serial_u64, dev_id)
