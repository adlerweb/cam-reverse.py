"""LAN discovery. Port of ``discovery.ts`` on asyncio.

Broadcasts ``LanSearch`` to every configured discovery IP on UDP/32108 every
3s; each ``PunchPkt`` reply emits a ``discover`` event with (addr, DevSerial).
"""
from __future__ import annotations

import asyncio
from typing import List

from . import settings
from .datatypes import Commands
from .dataview import DV
from .event_emitter import EventEmitter
from .impl import create_LanSearch, parse_PunchPkt
from .logger import logger

SEND_PORT = 32108


def _handle_incoming_punch(msg: bytes, ee: EventEmitter, rinfo) -> None:
    dv = DV(bytearray(msg))
    cmd_id = dv.read_u16()
    if cmd_id != Commands["PunchPkt"]:
        return
    if rinfo[0] in settings.config["blacklisted_ips"]:
        logger.debug(f"Dropping packet of blacklisted IP: {rinfo[0]}")
        return
    logger.debug("Received a PunchPkt message")
    ee.emit("discover", rinfo, parse_PunchPkt(dv))


class _DiscoveryProtocol(asyncio.DatagramProtocol):
    def __init__(self, ee: EventEmitter):
        self.ee = ee

    def datagram_received(self, data: bytes, addr) -> None:
        _handle_incoming_punch(data, self.ee, addr)

    def error_received(self, exc: Exception) -> None:
        logger.error(f"sock error:\n{exc}")


async def _run_discovery(discovery_ips: List[str], ee: EventEmitter) -> None:
    loop = asyncio.get_running_loop()
    transport, _ = await loop.create_datagram_endpoint(
        lambda: _DiscoveryProtocol(ee),
        local_addr=("0.0.0.0", 0),
        allow_broadcast=True,
    )
    ls_buf = create_LanSearch().to_bytes()
    tasks: List[asyncio.Task] = []

    def _probe(ip: str) -> None:
        logger.log("trace", f">> LanSearch [{ip}]")
        try:
            transport.sendto(ls_buf, (ip, SEND_PORT))
        except OSError as exc:
            logger.debug(f"send to {ip} failed: {exc}")

    async def _blast(ip: str) -> None:
        while True:
            _probe(ip)
            await asyncio.sleep(3)

    active = set()

    def _add_target(ip: str) -> None:
        if ip in active:
            _probe(ip)  # already tracked; nudge immediately (e.g. reconnect)
            return
        active.add(ip)
        logger.info(f"Searching for devices on {ip}")
        tasks.append(loop.create_task(_blast(ip)))

    for ip in discovery_ips:
        _add_target(ip)

    # Allow new discovery targets (manual IP / broadcast) to be added at runtime.
    ee.on("add_target", _add_target)

    def _on_close() -> None:
        for t in tasks:
            t.cancel()
        transport.close()

    ee.on("close", _on_close)


def discover_devices(discovery_ips: List[str]) -> EventEmitter:
    ee = EventEmitter()
    asyncio.get_event_loop().create_task(_run_discovery(discovery_ips, ee))
    return ee
