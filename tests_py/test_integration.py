"""Integration test ported from tests/integration.test.js.

Stands up a fake camera on UDP/32108 (loopback) and drives discovery end to end.
"""
import asyncio

import pytest

from cam_reverse.datatypes import Commands
from cam_reverse.dataview import DV
from cam_reverse.discovery import discover_devices
from cam_reverse.logger import build_logger
from cam_reverse.mock_server import mock_server


@pytest.mark.asyncio
async def test_discovers_a_device():
    build_logger("warning")
    expected_serial = "BATD156362WONJM"
    punch_pkt = bytes.fromhex("f14100144241544400000000000262ca574f4e4a4d000000")

    def on_message(dv: DV):
        if dv.read_u16() == Commands["LanSearch"]:
            return [punch_pkt]
        return []

    transport = await mock_server(on_message)
    got = asyncio.get_event_loop().create_future()

    ev = discover_devices(["127.0.0.1"])
    ev.on("discover", lambda rinfo, dev: got.set_result(dev.dev_id) if not got.done() else None)

    try:
        dev_id = await asyncio.wait_for(got, timeout=5)
        assert dev_id == expected_serial
    finally:
        ev.emit("close")
        transport.close()
