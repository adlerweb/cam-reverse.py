"""Minimal EXIF orientation segment injection. Port of ``exif.ts``."""
from __future__ import annotations


def create_exif_orientation(orientation: int) -> bytes:
    tiff_header = bytes.fromhex("49492A0008000000")
    ifd_entry = (
        bytes.fromhex("0100")  # number of IFD entries
        + bytes.fromhex("1201030001000000")  # tag, type, count
        + bytes([orientation & 0xFF])  # orientation value
        + bytes.fromhex("0000")  # no more IFDs
        + bytes.fromhex("0000000000")  # padding??
    )
    exif_data = bytes.fromhex("457869660000") + tiff_header + ifd_entry
    seg_len = len(exif_data) + 2
    exif_header = bytes.fromhex("FFE1") + bytes([(seg_len >> 8) & 0xFF, seg_len & 0xFF])
    return exif_header + exif_data


def add_exif_to_jpeg(jpeg_data: bytes, exif_segment: bytes) -> bytes:
    if bytes.fromhex("FFE1") in jpeg_data:
        raise ValueError("JPEG already contains EXIF segment")
    soi_end = 2  # after FFD8
    return jpeg_data[:soi_end] + exif_segment + jpeg_data[soi_end:]
