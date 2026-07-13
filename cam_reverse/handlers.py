"""Incoming packet handlers + payload parsers. Port of ``handlers.ts``."""
from __future__ import annotations

from dataclasses import dataclass
from typing import List

from . import settings
from .crypto import xq_bytes_dec
from .datatypes import Commands, CommandsByValue, ControlCommands
from .dataview import DV
from .impl import DevSerial, SendListWifi, SendUsrChk, create_P2pRdy
from .logger import logger

_ControlByValue = {v: k for k, v in ControlCommands.items()}


def not_impl(session, dv: DV, rinfo=None) -> None:
    raw = dv.read_u16()
    cmd = CommandsByValue.get(raw)
    logger.debug(f"^^ {cmd} ({raw:x}) and it's not implemented yet")


def noop(session=None, dv=None, rinfo=None) -> None:
    pass


def _create_p2p_alive_ack() -> DV:
    outbuf = DV.alloc(4)
    outbuf.write_u16(Commands["P2PAliveAck"])
    outbuf.add(2).write_u16(0)
    return outbuf


def handle_p2p_alive(session, dv: DV, rinfo=None) -> None:
    session.send(_create_p2p_alive_ack())


def handle_p2p_rdy(session, dv: DV, rinfo=None) -> None:
    # TODO - config
    session.send(SendUsrChk(session, "admin", "admin"))


def make_p2p_rdy(dev: DevSerial) -> DV:
    outbuf = DV.alloc(0x14)  # 8 = serial u64
    # The protocol expects a 4-byte prefix field; see the regression test
    # "replies properly to PunchPkt with 3-letters-long prefix".
    dev_prefix_length = 4
    outbuf.add(0).write_string(dev.prefix)
    outbuf.add(4).write_u64(dev.serial_u64)
    outbuf.add(8 + dev_prefix_length).write_string(dev.suffix)
    return create_P2pRdy(outbuf)


def sw_ver_to_string(swver: int) -> str:
    return (
        f"{(swver >> 24) & 255}."
        f"{(swver >> 16) & 255}."
        f"{(swver >> 8) & 255}."
        f"{swver & 255}"
    )


@dataclass
class DevStatus:
    charging: bool
    battery_mV: int
    dbm: int
    swver: str


def parse_dev_status_ack(dv: DV) -> DevStatus:
    charging = dv.add(0x28).read_u32le() & 1  # 0x14000101 v 0x14000100
    power = dv.add(0x18).read_u16le()  # milliVolts
    dbm = dv.add(0x24).read_u8() - 0x100  # 0xbf - 0x100 = -65 dBm
    n_swver = dv.add(0x14).read_u32le()
    return DevStatus(
        charging=charging > 0,
        battery_mV=power,
        dbm=dbm,
        swver=sw_ver_to_string(n_swver),
    )


@dataclass
class WifiListItem:
    ssid: str
    mac: str
    security: int
    dbm0: int
    dbm1: int
    mode: int
    channel: int


def parse_list_wifi(dv: DV) -> List[WifiListItem]:
    startat = 0x10
    msg_len = 0x5C  # 0x58 + 0x4 of the last u32
    msg_count = dv.add(startat).read_u32le()
    startat += 4
    items: List[WifiListItem] = []
    for _ in range(msg_count):
        if startat + msg_len > dv.byte_length:
            logger.warning("Wifi listing got cropped")
            break
        mac_bytes = dv.add(startat + 0x40).read_byte_array(6)
        item = WifiListItem(
            ssid=dv.add(startat).read_string(0x40),
            mac=":".join(f"{b:02x}" for b in mac_bytes),
            security=dv.add(startat + 0x48).read_u32le(),
            dbm0=dv.add(startat + 0x4C).read_u32le(),
            dbm1=dv.add(startat + 0x50).read_u32le(),
            mode=dv.add(startat + 0x54).read_u32le(),
            channel=dv.add(startat + 0x58).read_u32le(),
        )
        startat += msg_len
        items.append(item)
    return items


def create_response_for_control_command(session, dv: DV) -> List[DV]:
    start_type = dv.add(8).read_u16()  # 0xa11 on control
    cmd_id = dv.add(10).read_u16()
    payload_len = dv.add(0xC).read_u16le()
    if dv.byte_length > 20 and payload_len > dv.byte_length:
        logger.warning(f"Received a cropped payload: {payload_len} when packet is {dv.byte_length}")
        payload_len = dv.byte_length - 20

    if start_type != 0x110A:
        logger.error(f"Expected start_type to be 0xa11, got 0x{start_type:x}")
        return []

    rotate_chr = 4
    if payload_len > rotate_chr:
        # 20 = 16 (header) + 4 (??)
        xq_bytes_dec(dv.add(20), payload_len - 4, rotate_chr)

    if cmd_id == ControlCommands["ConnectUserAck"]:
        c = dv.add(0x18).read_byte_array(4)
        session.ticket = list(c)
        session.event_emitter.emit("login")
        return []

    if cmd_id == ControlCommands["DevStatusAck"]:
        status = parse_dev_status_ack(dv)
        logger.info(
            f"Camera {session.dev_name}: sw: {status.swver}, "
            f"{'' if status.charging else 'not '}charging, "
            f"battery at {status.battery_mV}mV, Wifi {status.dbm} dBm"
        )
        return []

    if cmd_id == ControlCommands["WifiSettingsAck"]:
        wifi_settings = {
            "enable": dv.add(0x14).read_u32(),
            "status": dv.add(0x18).read_u32(),
            "mode": dv.add(0x1C).read_u32le(),
            "channel": dv.add(0x20).read_u32(),
            "authtype": dv.add(0x24).read_u32(),
            "dhcp": dv.add(0x28).read_u32(),
            "ssid": dv.add(0x2C).read_string(0x20),
            "psk": dv.add(0x4C).read_string(0x80),
            "ip": dv.add(0xCC).read_string(0x10),
            "mask": dv.add(0xDC).read_string(0x10),
            "gw": dv.add(0xEC).read_string(0x10),
            "dns1": dv.add(0xFC).read_string(0x10),
            "dns2": dv.add(0x10C).read_string(0x10),
        }
        import json

        logger.info(f"Current Wifi settings: {json.dumps(wifi_settings, indent=2)}")
        return [SendListWifi(session)]

    if cmd_id == ControlCommands["ListWifiAck"]:
        if payload_len == 4:
            logger.debug("ListWifi returned []")
            return []
        items = parse_list_wifi(dv)
        session.event_emitter.emit("ListWifi", items)
        return []

    if cmd_id == ControlCommands["StartVideoAck"]:
        logger.debug("Start video ack")
        return []

    if cmd_id == ControlCommands["VideoParamSetAck"]:
        logger.debug("Video param set ack")
        return []

    logger.info(f"Unhandled control command: 0x{cmd_id:x}")
    return []


def _find_all_reset_markers(b: bytes) -> List[int]:
    # a reset marker is a byte 0xff followed by a byte 0xd0-0xd7
    ret = []
    for i in range(len(b) - 1):
        if b[i] == 0xFF and 0xD0 <= b[i + 1] <= 0xD7:
            ret.append(i)
    return ret


def _deal_with_data(session, dv: DV) -> None:
    pkt_len = dv.add(2).read_u16()

    # 12 = start of header (0x8) + header length (0x4)
    if pkt_len < 12:
        logger.log("trace", "Got a short Drw packet, ignoring")
        return

    FRAME_HEADER = b"\x55\xaa\x15\xa8"
    m_hdr = dv.add(8).read_byte_array(4)
    pkt_id = dv.add(6).read_u16()
    STREAM_TYPE_AUDIO = 0x06
    STREAM_TYPE_JPEG = 0x03

    def start_new_frame(buf: bytes) -> None:
        if len(session.cur_image) > 0 and not session.frame_is_bad:
            session.event_emitter.emit("frame")
        session.frame_was_fixed = False
        session.frame_is_bad = False
        session.cur_image = [bytes(buf)]
        session.rcv_seq_id = pkt_id

    is_framed = m_hdr.startswith(FRAME_HEADER)

    if is_framed:
        stream_type = dv.add(12).read_u8()
        if stream_type == STREAM_TYPE_AUDIO:
            audio_len = dv.add(8 + 16).read_u16le()
            # 8 for pkt header, 32 for stream_head_t
            audio_buf = dv.add(32 + 8).read_byte_array(audio_len)
            session.event_emitter.emit("audio", {"gap": False, "data": bytes(audio_buf)})
        elif stream_type == STREAM_TYPE_JPEG:
            to_read = pkt_len - 4 - 32
            if to_read > 0:
                # skip 8 (drw header) + 32 (data frame)
                data = dv.add(32 + 8).read_byte_array(to_read)
                start_new_frame(data)
        else:
            logger.debug(f"Ignoring data frame with stream type {stream_type} - not implemented")
        return

    JPEG_HEADER = b"\xff\xd8\xff\xdb"
    data = dv.add(8).read_byte_array(pkt_len - 4)
    is_new_image = m_hdr.startswith(JPEG_HEADER)

    if is_new_image:
        start_new_frame(data)
        return

    if pkt_id <= session.rcv_seq_id:
        # retransmit
        return

    b = bytes(data)

    if pkt_id > session.rcv_seq_id + 1:
        if not session.frame_is_bad:
            session.frame_is_bad = True
            logger.debug(f"Dropping corrupt frame {pkt_id}, expected {session.rcv_seq_id + 1}")

        # off by default: currently causes more distortion than dropped frames
        if not settings.config["cameras"].get(session.dev_name, {}).get("fix_packet_loss"):
            return

        if len(session.cur_image) <= 1:
            return  # header does not have markers

        last_frame_slice = session.cur_image[-1]
        markers = _find_all_reset_markers(last_frame_slice)
        if not markers:
            return
        last_reset_marker = markers[-1]

        first_markers = _find_all_reset_markers(b)
        if not first_markers:
            return
        first_reset_marker = first_markers[0]

        session.cur_image[-1] = last_frame_slice[:last_reset_marker]
        b = b[first_reset_marker:]
        session.frame_is_bad = False
        session.frame_was_fixed = True

    session.rcv_seq_id = pkt_id
    session.cur_image.append(b)


def _make_drw_ack(dv: DV) -> DV:
    pkt_id = dv.add(6).read_u16()
    m_stream = dv.add(5).read_u8()  # data = 1, control = 0
    item_count = 1  # TODO coalesce acks
    reply_len = item_count * 2 + 4  # 4 hdr, 2b per item
    outbuf = DV.alloc(32)
    outbuf.write_u16(Commands["DrwAck"])
    outbuf.add(2).write_u16(reply_len)
    outbuf.add(4).write_u8(0xD2)
    outbuf.add(5).write_u8(m_stream)
    outbuf.add(6).write_u16(item_count)
    for i in range(item_count):
        outbuf.add(8 + i * 2).write_u16(pkt_id)
    return outbuf


def handle_drw_ack(session, dv: DV, rinfo=None) -> None:
    ack_count = dv.add(6).read_u16()
    for i in range(ack_count):
        ack_id = dv.add(8 + i * 2).read_u16()
        session.ack_drw(ack_id)


def handle_drw(session, dv: DV, rinfo=None) -> None:
    session.send(_make_drw_ack(dv))

    m_stream = dv.add(5).read_u8()  # data = 1, control = 0
    if m_stream == 1:
        _deal_with_data(session, dv)
    elif m_stream == 0:
        for pkt in create_response_for_control_command(session, dv):
            session.send(pkt)
    else:
        logger.warning(f"Received a Drw packet with stream tag: {m_stream}, which is not implemented")


def handle_close(session, dv: DV, rinfo=None) -> None:
    session.send(_make_drw_ack(dv))
    logger.info("Requested to close connection")
    session.close()
