from __future__ import annotations

import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from realtime_runtime.interaction_state import (  # noqa: E402
    EventType,
    InteractionEvent,
    InteractionState,
    ReducerEffect,
    reduce_interaction,
)


class InteractionStateTests(unittest.TestCase):
    def test_seek_replay_and_speed_adjust_start_new_episode_without_closing_visit(self) -> None:
        initial = InteractionState()
        seek = reduce_interaction(initial, InteractionEvent(EventType.SEEK_COMMIT, 10))
        replay = reduce_interaction(seek.state, InteractionEvent(EventType.REPLAY, 20))
        speed = reduce_interaction(replay.state, InteractionEvent(EventType.SPEED_ADJUST, 30, playback_rate=1.5))

        self.assertTrue(seek.state.content_visit_open)
        self.assertEqual(2, seek.state.media_episode)
        self.assertEqual(3, replay.state.media_episode)
        self.assertEqual(4, speed.state.media_episode)
        self.assertIn(ReducerEffect.START_NEW_MEDIA_EPISODE, speed.effects)
        self.assertNotIn(ReducerEffect.CLOSE_CONTENT_VISIT, speed.effects)

    def test_swipe_creates_visit_boundary_but_background_preserves_existing_visit_evidence(self) -> None:
        initial = InteractionState()
        swipe = reduce_interaction(initial, InteractionEvent(EventType.SWIPE_NEXT, 10))
        background = reduce_interaction(swipe.state, InteractionEvent(EventType.BACKGROUND, 20))

        self.assertIn(ReducerEffect.CLOSE_CONTENT_VISIT, swipe.effects)
        self.assertIn(ReducerEffect.START_CONTENT_VISIT, swipe.effects)
        self.assertTrue(background.state.content_visit_open)
        self.assertNotIn(ReducerEffect.CLOSE_CONTENT_VISIT, background.effects)

    def test_engagement_and_comment_reading_remain_behavior_facts_not_learning_stage_transitions(self) -> None:
        opened = reduce_interaction(InteractionState(), InteractionEvent(EventType.OPEN_COMMENTS, 10))
        favorite = reduce_interaction(opened.state, InteractionEvent(EventType.FAVORITE, 20))

        self.assertIn(ReducerEffect.RECORD_INTERFACE_CONTEXT, opened.effects)
        self.assertIn(ReducerEffect.RECORD_ENGAGEMENT, favorite.effects)
        self.assertFalse(any(effect.name.startswith("OPEN_L") or effect.name.startswith("START_L") for effect in favorite.effects))


if __name__ == "__main__":
    unittest.main()
