"""Regression coverage for v2 PTS-gap recovery without pytest.

This test is intentionally standard-library only so the core safety property
can run in the current offline Python environment.
"""

from __future__ import annotations

import hashlib
import sqlite3
import sys
import tempfile
import unittest
from contextlib import closing
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.realtime_runtime.encoded_media_frame import (  # noqa: E402
    EncodedMediaFrame,
    EncodedMediaTrack,
    encode_encoded_media_frame,
)
from scripts.realtime_runtime.media_buffer import PcBufferedFragment  # noqa: E402
from scripts.realtime_runtime.media_security import AcceptedMediaFragment, MediaFragmentHeader  # noqa: E402
from scripts.realtime_runtime.v2_l0_media_processor import V2L0MediaProcessor  # noqa: E402


def _accepted(*, sequence: int, start_us: int, is_key_frame: bool) -> AcceptedMediaFragment:
    plaintext = encode_encoded_media_frame(
        EncodedMediaFrame(EncodedMediaTrack.VIDEO, start_us, 2_000, is_key_frame, b"annex-b-frame")
    )
    return AcceptedMediaFragment(
        header=MediaFragmentHeader(
            media_security_session_id="media-session-1",
            learner_id="learner-1",
            capture_session_id="capture-1",
            capture_consent_id="consent-1",
            consent_generation=1,
            route_lease_id="route-1",
            route_epoch=1,
            capture_epoch=2,
            sequence=sequence,
            pts_start_us=start_us,
            pts_end_us=start_us + 2_000,
            media_sha256=hashlib.sha256(plaintext).hexdigest(),
        ),
        plaintext=plaintext,
    )


def _buffered(accepted: AcceptedMediaFragment) -> PcBufferedFragment:
    header = accepted.header
    return PcBufferedFragment(
        fragment_id=f"fragment-{header.sequence}",
        sequence=header.sequence,
        start_pts_ns=header.pts_start_us * 1_000,
        end_pts_ns=header.pts_end_us * 1_000,
        media_hash=header.media_sha256,
        local_storage_hash="a" * 64,
        outbox_id="outbox-1",
        replay_idempotency_key=f"replay-{header.sequence}",
    )


class V2L0GapKeyframeTests(unittest.TestCase):
    def test_gap_recovery_rejects_non_key_frames_and_starts_a_new_episode_at_idr(self) -> None:
        calls: list[tuple[str, bool]] = []
        first = _accepted(sequence=0, start_us=10_000, is_key_frame=True)
        gap = _accepted(sequence=1, start_us=13_000, is_key_frame=False)
        unsafe_p_frame = _accepted(sequence=2, start_us=15_000, is_key_frame=False)
        recovery_idr = _accepted(sequence=3, start_us=17_000, is_key_frame=True)

        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            processor = V2L0MediaProcessor(
                root=root / "private-v2-l0",
                semantic_ledger_path=root / "semantic.sqlite3",
                video_decoder=lambda key, _payload, is_key: calls.append((key, is_key)) or b"decoded",
            )

            self.assertEqual("DECODED_L0", processor.process(first, _buffered(first)).state)
            self.assertEqual("VIDEO_GAP_QUARANTINED_L0", processor.process(gap, _buffered(gap)).state)
            self.assertEqual("WAITING_KEYFRAME_L0", processor.process(unsafe_p_frame, _buffered(unsafe_p_frame)).state)
            self.assertEqual("DECODED_L0", processor.process(recovery_idr, _buffered(recovery_idr)).state)
            self.assertEqual(
                [
                    ("capture-1:consent-1:1:2:0", True),
                    ("capture-1:consent-1:1:2:1", True),
                ],
                calls,
            )
            # ``sqlite3.Connection`` commits on context exit but does not
            # close on Windows; close before TemporaryDirectory cleanup.
            with closing(sqlite3.connect(root / "semantic.sqlite3")) as connection:
                rows = connection.execute(
                    "SELECT episode_id, start_pts_ns FROM semantic_facts ORDER BY start_pts_ns"
                ).fetchall()
            self.assertEqual(
                [
                    ("v2-capture:capture-1:epoch:2:continuity:0", 10_000_000),
                    ("v2-capture:capture-1:epoch:2:continuity:1", 17_000_000),
                ],
                rows,
            )


if __name__ == "__main__":
    unittest.main()
