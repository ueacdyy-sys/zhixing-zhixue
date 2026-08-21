from __future__ import annotations

import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from realtime_runtime.contracts import (  # noqa: E402
    ContentEpisode,
    EpisodeStatus,
    SemanticCompleteness,
    SemanticScope,
    SemanticScopeStability,
    SourceKind,
)


HASH_A = "a" * 64
HASH_B = "b" * 64


class ContentEpisodeContractTests(unittest.TestCase):
    def _episode(self, **overrides: object) -> ContentEpisode:
        fields: dict[str, object] = {
            "episode_id": "episode-1",
            "learner_id": "learner-1",
            "session_id": "session-1",
            "capture_consent_id": "consent-1",
            "consent_generation": 1,
            "source_kind": SourceKind.PHONE_SCREEN,
            "start_pts_ns": 100,
            "continuity_start_pts_ns": 100,
            "end_pts_ns": None,
            "status": EpisodeStatus.OPEN,
            "boundary_confidence": 0.93,
            "boundary_reason": "CONTENT_CONTINUITY",
            "resolver_version": "episode-boundary.v2",
            "policy_version": "capture-policy.v2",
        }
        fields.update(overrides)
        return ContentEpisode(**fields)  # type: ignore[arg-type]

    def test_episode_records_continuous_content_boundary_without_platform_video_id(self) -> None:
        episode = self._episode()

        self.assertEqual("episode-1", episode.episode_id)
        self.assertIsNone(episode.end_pts_ns)
        self.assertEqual(EpisodeStatus.OPEN, episode.status)

    def test_ambiguous_episode_cannot_host_a_stable_scope(self) -> None:
        episode = self._episode(
            episode_id="episode-ambiguous",
            end_pts_ns=200,
            status=EpisodeStatus.EPISODE_AMBIGUOUS,
            boundary_confidence=0.25,
            boundary_reason="SPLIT_SCREEN",
        )

        with self.assertRaisesRegex(ValueError, "stable_scope_requires_non_ambiguous_episode"):
            SemanticScope(
                scope_id="scope-1",
                episode=episode,
                start_pts_ns=100,
                end_pts_ns=200,
                scope_hash=HASH_A,
                semantic_lineage_id="lineage-1",
                completeness=SemanticCompleteness.WINDOW_COMPLETE,
                stability=SemanticScopeStability.STABLE,
                semantic_revision=1,
                event_time_watermark_ns=200,
            )

    def test_revised_scope_requires_an_immutable_predecessor(self) -> None:
        episode = self._episode(
            end_pts_ns=300,
            status=EpisodeStatus.CLOSED,
            boundary_reason="CONTENT_SWITCH",
        )

        with self.assertRaisesRegex(ValueError, "revised_scope_requires_predecessor"):
            SemanticScope(
                scope_id="scope-revised",
                episode=episode,
                start_pts_ns=100,
                end_pts_ns=200,
                scope_hash=HASH_A,
                semantic_lineage_id="lineage-1",
                completeness=SemanticCompleteness.WINDOW_COMPLETE,
                stability=SemanticScopeStability.REVISED,
                semantic_revision=2,
                event_time_watermark_ns=200,
            )

    def test_stable_scope_requires_complete_range_and_watermark(self) -> None:
        episode = self._episode()

        with self.assertRaisesRegex(ValueError, "stable_scope_requires_complete_range"):
            SemanticScope(
                scope_id="scope-incomplete",
                episode=episode,
                start_pts_ns=100,
                end_pts_ns=200,
                scope_hash=HASH_A,
                semantic_lineage_id="lineage-1",
                completeness=SemanticCompleteness.IN_PROGRESS,
                stability=SemanticScopeStability.STABLE,
                semantic_revision=1,
                event_time_watermark_ns=199,
            )

    def test_episode_must_bind_learner_consent_and_policy_scope(self) -> None:
        for field in ("learner_id", "capture_consent_id", "policy_version"):
            with self.subTest(field=field), self.assertRaisesRegex(ValueError, "episode_scope_invalid"):
                self._episode(**{field: ""})
        with self.assertRaisesRegex(ValueError, "episode_consent_generation_invalid"):
            self._episode(consent_generation=0)

    def test_closed_episode_requires_a_final_pts(self) -> None:
        with self.assertRaisesRegex(ValueError, "closed_episode_requires_end_pts"):
            self._episode(status=EpisodeStatus.CLOSED, boundary_reason="CONTENT_SWITCH")

    def test_gap_detected_episode_cannot_emit_stable_scope_until_continuity_recovers(self) -> None:
        episode = self._episode(status=EpisodeStatus.GAP_DETECTED, boundary_reason="MEDIA_GAP")

        with self.assertRaisesRegex(ValueError, "stable_scope_requires_continuous_episode"):
            SemanticScope(
                scope_id="scope-gap",
                episode=episode,
                start_pts_ns=100,
                end_pts_ns=200,
                scope_hash=HASH_A,
                semantic_lineage_id="lineage-1",
                completeness=SemanticCompleteness.WINDOW_COMPLETE,
                stability=SemanticScopeStability.STABLE,
                semantic_revision=1,
                event_time_watermark_ns=200,
            )

    def test_recovered_episode_cannot_create_scope_across_prior_gap(self) -> None:
        episode = self._episode(
            continuity_start_pts_ns=201,
            boundary_reason="RECOVERED_AFTER_MEDIA_GAP",
        )

        with self.assertRaisesRegex(ValueError, "scope_crosses_episode_gap"):
            SemanticScope(
                scope_id="scope-cross-gap",
                episode=episode,
                start_pts_ns=100,
                end_pts_ns=250,
                scope_hash=HASH_A,
                semantic_lineage_id="lineage-1",
                completeness=SemanticCompleteness.WINDOW_COMPLETE,
                stability=SemanticScopeStability.STABLE,
                semantic_revision=1,
                event_time_watermark_ns=250,
            )

    def test_revised_scope_requires_predecessor_hash(self) -> None:
        episode = self._episode(end_pts_ns=300, status=EpisodeStatus.CLOSED, boundary_reason="CONTENT_SWITCH")

        with self.assertRaisesRegex(ValueError, "revised_scope_requires_predecessor_hash"):
            SemanticScope(
                scope_id="scope-revised-without-hash",
                episode=episode,
                start_pts_ns=100,
                end_pts_ns=200,
                scope_hash=HASH_B,
                semantic_lineage_id="lineage-1",
                completeness=SemanticCompleteness.WINDOW_COMPLETE,
                stability=SemanticScopeStability.REVISED,
                semantic_revision=2,
                event_time_watermark_ns=200,
                replaces_scope_id="scope-1",
            )


if __name__ == "__main__":
    unittest.main()
