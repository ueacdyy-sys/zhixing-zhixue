from __future__ import annotations

import struct

import pytest

from scripts.realtime_runtime.encoded_media_frame import (
    EncodedMediaFrame,
    EncodedMediaTrack,
    decode_encoded_media_frame,
    encode_encoded_media_frame,
)


def test_encoded_media_frame_round_trip_preserves_track_pts_and_keyframe() -> None:
    frame = EncodedMediaFrame(
        track=EncodedMediaTrack.VIDEO,
        pts_us=100_000,
        duration_us=33_333,
        is_key_frame=True,
        payload=b"h264-access-unit",
    )

    encoded = encode_encoded_media_frame(frame)

    assert decode_encoded_media_frame(encoded) == frame


def test_encoded_media_frame_rejects_truncated_or_invalid_duration() -> None:
    frame = EncodedMediaFrame(EncodedMediaTrack.AUDIO, 10, 20, False, b"aac")
    encoded = encode_encoded_media_frame(frame)

    with pytest.raises(ValueError, match="encoded_media_frame_truncated"):
        decode_encoded_media_frame(encoded[:-1])
    with pytest.raises(ValueError, match="encoded_media_frame_duration_invalid"):
        decode_encoded_media_frame(encoded.replace(struct.pack(">q", 20), struct.pack(">q", 0), 1))


def test_encoded_media_frame_rejects_unknown_track_and_trailing_bytes() -> None:
    encoded = bytearray(encode_encoded_media_frame(EncodedMediaFrame(EncodedMediaTrack.VIDEO, 1, 2, False, b"x")))
    track_offset = len(b"ZHIXING_ENCODED_MEDIA_FRAME.v1\n")
    encoded[track_offset] = 9
    with pytest.raises(ValueError, match="encoded_media_frame_track_invalid"):
        decode_encoded_media_frame(bytes(encoded))

    with pytest.raises(ValueError, match="encoded_media_frame_trailing_bytes"):
        decode_encoded_media_frame(encode_encoded_media_frame(EncodedMediaFrame(EncodedMediaTrack.VIDEO, 1, 2, False, b"x")) + b"extra")
