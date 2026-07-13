"""A thin big-/little-endian byte cursor.

Port of the ``DataView`` monkey-patch from ``shim.ts``. The original relied on
JS's ``DataView`` (big-endian by default) plus ``add(offset)`` to create a view
at a sub-offset that shares the same backing buffer. We reproduce that here: a
``DV`` wraps a ``bytearray`` and an offset, and ``add`` returns another ``DV``
over the *same* ``bytearray`` so in-place mutation (e.g. the Xq de/obfuscation)
propagates to the original, exactly like the JS code depends on.
"""
from __future__ import annotations

import struct
from typing import Iterable, Union

BytesLike = Union[bytes, bytearray, "Iterable[int]"]


class DV:
    __slots__ = ("buf", "offset")

    def __init__(self, buf: Union[bytes, bytearray], offset: int = 0):
        # Always hold a bytearray so writes/decryption work in place.
        if not isinstance(buf, bytearray):
            buf = bytearray(buf)
        self.buf = buf
        self.offset = offset

    @classmethod
    def alloc(cls, size: int) -> "DV":
        return cls(bytearray(size), 0)

    def add(self, offset: int) -> "DV":
        return DV(self.buf, self.offset + offset)

    @property
    def byte_length(self) -> int:
        return len(self.buf) - self.offset

    # -- reads --------------------------------------------------------------
    def read_u8(self) -> int:
        return self.buf[self.offset]

    def read_u16(self) -> int:
        return struct.unpack_from(">H", self.buf, self.offset)[0]

    def read_u16le(self) -> int:
        return struct.unpack_from("<H", self.buf, self.offset)[0]

    def read_u32(self) -> int:
        return struct.unpack_from(">I", self.buf, self.offset)[0]

    def read_u32le(self) -> int:
        return struct.unpack_from("<I", self.buf, self.offset)[0]

    def read_u64(self) -> int:
        return struct.unpack_from(">Q", self.buf, self.offset)[0]

    def read_byte_array(self, length: int) -> bytes:
        return bytes(self.buf[self.offset : self.offset + length])

    def read_string(self, length: int) -> str:
        raw = bytes(self.buf[self.offset : self.offset + length])
        nul = raw.find(0)
        if nul != -1:
            raw = raw[:nul]
        return raw.decode("latin-1")

    # -- writes -------------------------------------------------------------
    def write_u8(self, val: int) -> None:
        self.buf[self.offset] = val & 0xFF

    def write_u16(self, val: int) -> None:
        struct.pack_into(">H", self.buf, self.offset, val & 0xFFFF)

    def write_u32(self, val: int) -> None:
        struct.pack_into(">I", self.buf, self.offset, val & 0xFFFFFFFF)

    def write_u64(self, val: int) -> None:
        struct.pack_into(">Q", self.buf, self.offset, val & 0xFFFFFFFFFFFFFFFF)

    def write_byte_array(self, arr: BytesLike) -> None:
        data = bytes(arr)
        self.buf[self.offset : self.offset + len(data)] = data

    def write_string(self, s: str) -> None:
        self.write_byte_array(s.encode("latin-1"))

    def starts_with(self, arr: BytesLike) -> bool:
        arr = bytes(arr)
        if self.byte_length < len(arr):
            return False
        return self.buf[self.offset : self.offset + len(arr)] == arr

    def to_bytes(self) -> bytes:
        """The datagram to actually put on the wire (from offset to end)."""
        return bytes(self.buf[self.offset :])
