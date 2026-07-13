"""The "Xq" payload obfuscation used on control-command payloads > 4 bytes.

Port of the two functions in ``func_replacements.js`` that the real client
actually uses (the rest of that file was Frida scratch work). Both mutate the
buffer in place through the shared-backing-buffer ``DV``.
"""
from __future__ import annotations

from .dataview import DV


def _flip_low_bit(b: int) -> int:
    return b - 1 if (b & 1) != 0 else b + 1


def xq_bytes_dec(inoutbuf: DV, buflen: int, rotate: int) -> None:
    new_buf = bytearray(buflen)
    for i in range(buflen):
        new_buf[i] = _flip_low_bit(inoutbuf.add(i).read_u8()) & 0xFF
    for i in range(rotate, buflen):
        inoutbuf.add(i).write_u8(new_buf[i - rotate])
    for i in range(rotate):
        inoutbuf.add(i).write_u8(new_buf[buflen - rotate + i])


def xq_bytes_enc(inoutbuf: DV, buflen: int, rotate: int) -> None:
    new_buf = bytearray(buflen)
    for i in range(buflen):
        new_buf[i] = _flip_low_bit(inoutbuf.add(i).read_u8()) & 0xFF
    for i in range(buflen - rotate):
        inoutbuf.add(i).write_u8(new_buf[i + rotate])
    for i in range(rotate):
        inoutbuf.add(buflen - rotate + i).write_u8(new_buf[i])
