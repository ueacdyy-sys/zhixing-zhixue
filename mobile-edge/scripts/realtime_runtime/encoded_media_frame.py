"""Strict decoder for the Android RTSP encoded-frame v2 payload envelope."""

from __future__ import annotations

import struct
from dataclasses import dataclass
from enum import IntEnum


MAGIC = b"ZHIXING_ENCODED_MEDIA_FRAME.v1\n"
MAX_FRAME_BYTES = 16 * 1024 * 1024


class EncodedMediaTrack(IntEnum):
    VIDEO = 1
    AUDIO = 2


@dataclass(frozen=True)
class EncodedMediaFrame:
    track: EncodedMediaTrack
    pts_us: int
    duration_us: int
    is_key_frame: bool
    payload: bytes


def encode_encoded_media_frame(frame: EncodedMediaFrame) -> bytes:
    if frame.pts_us < 0 or frame.duration_us <= 0:
        raise ValueError("encoded_media_frame_duration_invalid")
    if not frame.payload or len(frame.payload) > MAX_FRAME_BYTES:
        raise ValueError("encoded_media_frame_payload_invalid")
    try:
        track = EncodedMediaTrack(frame.track)
    except ValueError as error:
        raise ValueError("encoded_media_frame_track_invalid") from error
    return (
        MAGIC
        + struct.pack(">Bqq?I", int(track), frame.pts_us, frame.duration_us, frame.is_key_frame, len(frame.payload))
        + frame.payload
    )


def decode_encoded_media_frame(value: bytes) -> EncodedMediaFrame:
    if not value.startswith(MAGIC):
        raise ValueError("encoded_media_frame_magic_invalid")
    offset = len(MAGIC)
    header_size = struct.calcsize(">Bqq?I")
    if len(value) < offset + header_size:
        raise ValueError("encoded_media_frame_truncated")
    track_raw, pts_us, duration_us, is_key_frame, payload_size = struct.unpack_from(">Bqq?I", value, offset)
    try:
        track = EncodedMediaTrack(track_raw)
    except ValueError as error:
        raise ValueError("encoded_media_frame_track_invalid") from error
    if pts_us < 0 or duration_us <= 0:
        raise ValueError("encoded_media_frame_duration_invalid")
    if payload_size <= 0 or payload_size > MAX_FRAME_BYTES:
        raise ValueError("encoded_media_frame_payload_invalid")
    payload_start = offset + header_size
    payload_end = payload_start + payload_size
    if len(value) < payload_end:
        raise ValueError("encoded_media_frame_truncated")
    if len(value) != payload_end:
        raise ValueError("encoded_media_frame_trailing_bytes")
    return EncodedMediaFrame(track, pts_us, duration_us, is_key_frame, value[payload_start:payload_end])
