from __future__ import annotations

import sqlite3
import sys
import tempfile
import unittest
from contextlib import closing
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from run_realtime_e2e import _counts  # noqa: E402


class RealtimeE2ESettlementTests(unittest.TestCase):
    def test_incomplete_evidence_is_reported_but_does_not_be_counted_as_fusion_work(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            ledger_path = Path(temp_dir) / "ledger.sqlite3"
            with closing(sqlite3.connect(ledger_path)) as connection:
                connection.executescript(
                    """
                    CREATE TABLE semantic_windows (fusion_mode TEXT NOT NULL, fused_at_ns INTEGER);
                    CREATE TABLE jobs (state TEXT NOT NULL);
                    """
                )
                connection.executemany(
                    "INSERT INTO semantic_windows VALUES (?, ?)",
                    (("TRIMODAL", 10), ("EVIDENCE_INCOMPLETE", None)),
                )
                connection.commit()

            counts = _counts(ledger_path)

        self.assertEqual(2, counts["windows"])
        self.assertEqual(1, counts["fusion_eligible_windows"])
        self.assertEqual(1, counts["evidence_incomplete_windows"])
        self.assertEqual(1, counts["fused"])
        self.assertEqual(0, counts["unresolved_jobs"])


if __name__ == "__main__":
    unittest.main()
