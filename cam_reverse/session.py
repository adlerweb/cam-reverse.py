"""Per-camera session: handshake, keepalive, Drw retransmit. Port of the
``makeSession`` machinery in ``session.ts``, on asyncio instead of node's
``dgram`` + ``setInterval``.

Each session owns one connected UDP datagram endpoint. Two background tasks
mirror the TS timers: one sends ``P2PAlive`` / enforces the timeout, the other
retransmits un-acked Drw packets with a fresh command id.
"""
from __future__ import annotations

import asyncio
import time
from typing import Callable, Dict, List, Tuple

from .datatypes import Commands, CommandsByValue
from .dataview import DV
from .event_emitter import EventEmitter
from .handlers import (
    handle_close,
    handle_drw,
    handle_drw_ack,
    handle_p2p_alive,
    handle_p2p_rdy,
    make_p2p_rdy,
    noop,
    not_impl,
)
from .impl import (
    DevSerial,
    SendStartVideo,
    SendVideoResolution,
    SendWifiDetails,
    create_P2pAlive,
)
from .logger import logger


def _now_ms() -> float:
    return time.time() * 1000


class _SessionProtocol(asyncio.DatagramProtocol):
    def __init__(self, session: "Session"):
        self.session = session

    def connection_made(self, transport: asyncio.DatagramTransport) -> None:
        s = self.session
        s.transport = transport
        # equivalent to the TS socket "listening" event
        s.send(make_p2p_rdy(s.dev))
        s.started = True
        loop = asyncio.get_event_loop()
        s._timers = [
            loop.create_task(s._sess_timer()),
            loop.create_task(s._resend_timer()),
        ]

    def datagram_received(self, data: bytes, addr) -> None:
        self.session._handle_incoming(data, addr)

    def error_received(self, exc: Exception) -> None:
        logger.error(f"sock error:\n{exc}")


class Session:
    def __init__(
        self,
        handlers: Dict[str, Callable],
        dev: DevSerial,
        addr: Tuple[str, int],
        on_login: Callable[["Session"], None],
        timeout_ms: int,
    ):
        self.handlers = handlers
        self.dev = dev
        self.dst_ip = addr[0]
        self.port = addr[1]
        self.timeout_ms = timeout_ms
        self.on_login = on_login

        self.event_emitter = EventEmitter()
        self.outgoing_command_id = 0
        self.ticket: List[int] = [0, 0, 0, 0]
        self.last_received_packet = 0.0
        self.connected = True
        self.dev_name = dev.dev_id
        self.started = False
        self.unacked_drw: Dict[int, dict] = {}
        self.cur_image: List[bytes] = []
        self.rcv_seq_id = 0
        self.frame_is_bad = False
        self.frame_was_fixed = False
        self.transport: asyncio.DatagramTransport = None
        self._timers: List[asyncio.Task] = []

        self.event_emitter.on("disconnect", self._on_disconnect)
        self.event_emitter.on("login", self._on_login)

    async def _connect(self) -> None:
        loop = asyncio.get_running_loop()
        await loop.create_datagram_endpoint(
            lambda: _SessionProtocol(self),
            remote_addr=(self.dst_ip, self.port),
        )

    # -- outgoing -----------------------------------------------------------
    def send(self, msg: DV) -> None:
        raw = msg.read_u16()
        cmd = CommandsByValue.get(raw)
        # a Drw "send command" (not an ack) -> remember it for retransmit
        if raw == 0xF1D0 and msg.add(4).read_u8() == 0xD1:
            packet_id = msg.add(6).read_u16()
            logger.debug(f"Sending Drw Packet with id {packet_id}")
            self.unacked_drw[packet_id] = {"sent_ts": _now_ms(), "data": msg}
        logger.log("trace", f">> {cmd}")
        if self.transport is not None:
            self.transport.sendto(msg.to_bytes())

    def ack_drw(self, id: int) -> None:
        logger.debug(f"Removing {id} from pending")
        self.unacked_drw.pop(id, None)

    def close(self) -> None:
        self.event_emitter.emit("disconnect")

    # -- incoming -----------------------------------------------------------
    def _handle_incoming(self, msg: bytes, rinfo) -> None:
        dv = DV(bytearray(msg))
        raw = dv.read_u16()
        cmd = CommandsByValue.get(raw)
        logger.log("trace", f"<< {cmd}")
        handler = self.handlers.get(cmd, not_impl)
        handler(self, dv, rinfo)
        if raw != Commands["P2PAlive"] and raw != Commands["P2PAliveAck"]:
            self.last_received_packet = _now_ms()

    # -- timers -------------------------------------------------------------
    async def _sess_timer(self) -> None:
        while True:
            await asyncio.sleep(0.4)
            if not self.started:
                continue
            delta = _now_ms() - self.last_received_packet
            if delta > 600:
                self.send(create_P2pAlive())
            if delta > self.timeout_ms:
                logger.warning(f"Camera {self.dev_name} timed out")
                self.event_emitter.emit("disconnect")
                return

    async def _resend_timer(self) -> None:
        while True:
            await asyncio.sleep(0.5)
            now = _now_ms()
            for key, value in list(self.unacked_drw.items()):
                if now - value["sent_ts"] > 100:
                    data = value["data"]
                    pkt_id = data.add(6).read_u16()
                    logger.debug(f"Resending packet {pkt_id} as {self.outgoing_command_id}")
                    data.add(6).write_u16(self.outgoing_command_id)
                    self.outgoing_command_id += 1
                    self.unacked_drw.pop(key, None)
                    self.send(data)

    # -- event handlers -----------------------------------------------------
    def _on_disconnect(self) -> None:
        if not self.connected:
            return
        logger.info(f"Disconnected from camera {self.dev_name} at {self.dst_ip}")
        self.dst_ip = "0.0.0.0"
        self.connected = False
        for t in self._timers:
            t.cancel()
        self._timers = []
        if self.transport is not None:
            self.transport.close()

    def _on_login(self) -> None:
        logger.info(f"Logging in to camera {self.dev_name}")
        self.on_login(self)


def make_session(
    handlers: Dict[str, Callable],
    dev: DevSerial,
    addr: Tuple[str, int],
    on_login: Callable[[Session], None],
    timeout_ms: int,
) -> Session:
    """Construct a session and schedule its UDP endpoint.

    Returns synchronously (like the TS version) so the caller can attach event
    handlers before the connect task runs on the next loop turn.
    """
    session = Session(handlers, dev, addr, on_login, timeout_ms)
    asyncio.get_event_loop().create_task(session._connect())
    return session


def configure_wifi(ssid: str, password: str, channel: int) -> Callable[[Session], None]:
    def _apply(s: Session) -> None:
        s.send(SendWifiDetails(s, ssid, password, channel, True))

    return _apply


def start_video_stream(s: Session) -> None:
    for pkt in SendVideoResolution(s, 2):  # 640x480
        s.send(pkt)
    s.send(SendStartVideo(s))


# Command-name -> handler, mirroring the TS `Handlers` record.
Handlers: Dict[str, Callable] = {
    "PunchPkt": not_impl,
    "P2PAlive": handle_p2p_alive,
    "P2pRdy": handle_p2p_rdy,
    "DrwAck": handle_drw_ack,
    "Drw": handle_drw,
    "Close": handle_close,
    "P2PAliveAck": noop,
    "LanSearchExt": not_impl,
    "LanSearch": not_impl,
    "Hello": not_impl,
    "P2pReq": not_impl,
    "LstReq": not_impl,
    "PunchTo": not_impl,
    "HelloAck": not_impl,
    "RlyTo": not_impl,
    "DevLgnAck": not_impl,
    "P2PReqAck": not_impl,
    "ListenReqAck": not_impl,
    "RlyHelloAck": not_impl,
    "RlyHelloAck2": not_impl,
}
