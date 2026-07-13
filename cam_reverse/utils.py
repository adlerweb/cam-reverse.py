"""Byte-order helpers. Port of the pieces of ``utils.js`` used by the client.

The Frida-only ``sprintf``/``placeholderTypes`` helpers are intentionally left
out; they were debugging tooling, not part of the running client.
"""


def u16_swap(x: int) -> int:
    return ((x & 0xFF00) >> 8) | ((x & 0x00FF) << 8)


def u32_swap(x: int) -> int:
    return (
        ((x & 0xFF000000) >> 24)
        | ((x & 0x00FF0000) >> 8)
        | ((x & 0x0000FF00) << 8)
        | ((x & 0x000000FF) << 24)
    )
