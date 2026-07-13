"""A fake camera for tests. Port of ``mock_server.ts`` on asyncio.

``on_message`` receives a :class:`DV` and returns a list of ``bytes`` replies.
"""
from __future__ import annotations

import asyncio
from typing import Callable, List

from .dataview import DV

SEND_PORT = 32108


class _MockProtocol(asyncio.DatagramProtocol):
    def __init__(self, on_message: Callable[[DV], List[bytes]]):
        self.on_message = on_message
        self.transport = None

    def connection_made(self, transport) -> None:
        self.transport = transport

    def datagram_received(self, data: bytes, addr) -> None:
        dv = DV(bytearray(data))
        for out in self.on_message(dv):
            self.transport.sendto(bytes(out), addr)


async def mock_server(on_message: Callable[[DV], List[bytes]]):
    loop = asyncio.get_running_loop()
    transport, _ = await loop.create_datagram_endpoint(
        lambda: _MockProtocol(on_message),
        local_addr=("127.0.0.1", SEND_PORT),
    )
    return transport
