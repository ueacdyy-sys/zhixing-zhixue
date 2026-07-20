"""Platform-neutral media interaction state machine.

Adapters may observe only a subset of events (ADB touch today, Accessibility or
MediaSession tomorrow).  Missing observation is never invented; the reducer
only changes state from explicit event facts.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class EventType(str, Enum):
    PLAY = "PLAY"
    PAUSE = "PAUSE"
    SEEK_START = "SEEK_START"
    SEEK_COMMIT = "SEEK_COMMIT"
    HOLD_FAST_FORWARD_START = "HOLD_FAST_FORWARD_START"
    HOLD_FAST_FORWARD_END = "HOLD_FAST_FORWARD_END"
    SPEED_ADJUST = "SPEED_ADJUST"
    REPLAY = "REPLAY"
    LOOP = "LOOP"
    SWIPE_NEXT = "SWIPE_NEXT"
    SWIPE_PREVIOUS = "SWIPE_PREVIOUS"
    CLICK_RECOMMENDATION = "CLICK_RECOMMENDATION"
    RETURN_BACK = "RETURN_BACK"
    REFRESH_FEED = "REFRESH_FEED"
    BACKGROUND = "BACKGROUND"
    FOREGROUND = "FOREGROUND"
    LIKE = "LIKE"
    FAVORITE = "FAVORITE"
    REWARD = "REWARD"
    SHARE = "SHARE"
    DISINTEREST = "DISINTEREST"
    FOLLOW = "FOLLOW"
    OPEN_COMMENTS = "OPEN_COMMENTS"
    CLOSE_COMMENTS = "CLOSE_COMMENTS"
    SCROLL_COMMENTS = "SCROLL_COMMENTS"
    LIKE_COMMENT = "LIKE_COMMENT"
    REPLY_COMMENT = "REPLY_COMMENT"
    POST_COMMENT = "POST_COMMENT"
    TOGGLE_FULLSCREEN = "TOGGLE_FULLSCREEN"
    ADJUST_VOLUME_BRIGHTNESS = "ADJUST_VOLUME_BRIGHTNESS"
    TOGGLE_DANMAKU = "TOGGLE_DANMAKU"
    SEND_DANMAKU = "SEND_DANMAKU"
    CHANGE_RESOLUTION = "CHANGE_RESOLUTION"
    PROFILE_CLICK = "PROFILE_CLICK"
    EXPAND_DESCRIPTION = "EXPAND_DESCRIPTION"
    CLICK_COMMERCE_OR_AD = "CLICK_COMMERCE_OR_AD"
    SYSTEM_OVERLAY = "SYSTEM_OVERLAY"
    L1_PROMPT_OPENED = "L1_PROMPT_OPENED"
    L2_EXPLORATION_OPENED = "L2_EXPLORATION_OPENED"
    L3_GUIDED_PRACTICE_STARTED = "L3_GUIDED_PRACTICE_STARTED"
    L4_SELF_PRACTICE_STARTED = "L4_SELF_PRACTICE_STARTED"


class PlaybackState(str, Enum):
    PLAYING = "PLAYING"
    PAUSED = "PAUSED"
    SEEKING = "SEEKING"
    FAST_FORWARD = "FAST_FORWARD"
    BACKGROUND = "BACKGROUND"
    ENDED = "ENDED"


class FocusSurface(str, Enum):
    VIDEO = "VIDEO"
    COMMENTS = "COMMENTS"
    FEED = "FEED"
    PROFILE = "PROFILE"
    OUTBOUND = "OUTBOUND"
    NONE = "NONE"


class ReducerEffect(str, Enum):
    RESUME_MEDIA_ANALYSIS = "RESUME_MEDIA_ANALYSIS"
    SUSPEND_MEDIA_ANALYSIS = "SUSPEND_MEDIA_ANALYSIS"
    CLOSE_CONTENT_VISIT = "CLOSE_CONTENT_VISIT"
    START_CONTENT_VISIT = "START_CONTENT_VISIT"
    START_NEW_MEDIA_EPISODE = "START_NEW_MEDIA_EPISODE"
    RECORD_ENGAGEMENT = "RECORD_ENGAGEMENT"
    RECORD_INTERFACE_CONTEXT = "RECORD_INTERFACE_CONTEXT"
    OPEN_L1_PROMPT = "OPEN_L1_PROMPT"
    OPEN_L2_EXPLORATION = "OPEN_L2_EXPLORATION"
    START_L3_GUIDED_PRACTICE = "START_L3_GUIDED_PRACTICE"
    START_L4_SELF_PRACTICE = "START_L4_SELF_PRACTICE"


@dataclass(frozen=True)
class InteractionEvent:
    event_type: EventType
    pc_monotonic_ns: int
    playback_rate: float | None = None

    def __post_init__(self) -> None:
        if self.pc_monotonic_ns < 0:
            raise ValueError("interaction_time_invalid")
        if self.playback_rate is not None and self.playback_rate <= 0:
            raise ValueError("playback_rate_invalid")


@dataclass(frozen=True)
class InteractionState:
    playback: PlaybackState = PlaybackState.PLAYING
    surface: FocusSurface = FocusSurface.VIDEO
    playback_rate: float = 1.0
    content_visit_open: bool = True
    media_episode: int = 1


@dataclass(frozen=True)
class Transition:
    state: InteractionState
    effects: tuple[ReducerEffect, ...]


ENGAGEMENT = {
    EventType.LIKE, EventType.FAVORITE, EventType.REWARD, EventType.SHARE,
    EventType.DISINTEREST, EventType.FOLLOW, EventType.LIKE_COMMENT,
    EventType.REPLY_COMMENT, EventType.POST_COMMENT, EventType.SEND_DANMAKU,
    EventType.EXPAND_DESCRIPTION, EventType.PROFILE_CLICK,
}
CONTENT_SWITCH = {
    EventType.SWIPE_NEXT, EventType.SWIPE_PREVIOUS, EventType.CLICK_RECOMMENDATION,
    EventType.RETURN_BACK, EventType.REFRESH_FEED, EventType.PROFILE_CLICK,
    EventType.CLICK_COMMERCE_OR_AD,
}


def reduce_interaction(state: InteractionState, event: InteractionEvent) -> Transition:
    """Reduce one explicit fact; do not infer a content ID, topic, or interest."""
    effects: list[ReducerEffect] = []
    next_state = state
    kind = event.event_type

    if kind is EventType.PLAY:
        next_state = InteractionState(PlaybackState.PLAYING, state.surface, state.playback_rate, state.content_visit_open, state.media_episode)
        effects.append(ReducerEffect.RESUME_MEDIA_ANALYSIS)
    elif kind is EventType.PAUSE:
        next_state = InteractionState(PlaybackState.PAUSED, state.surface, state.playback_rate, state.content_visit_open, state.media_episode)
        effects.append(ReducerEffect.SUSPEND_MEDIA_ANALYSIS)
    elif kind is EventType.SEEK_START:
        next_state = InteractionState(PlaybackState.SEEKING, state.surface, state.playback_rate, state.content_visit_open, state.media_episode)
        effects.append(ReducerEffect.SUSPEND_MEDIA_ANALYSIS)
    elif kind in {EventType.SEEK_COMMIT, EventType.REPLAY, EventType.LOOP}:
        next_state = InteractionState(PlaybackState.PLAYING, state.surface, state.playback_rate, state.content_visit_open, state.media_episode + 1)
        effects.extend((ReducerEffect.START_NEW_MEDIA_EPISODE, ReducerEffect.RESUME_MEDIA_ANALYSIS))
    elif kind is EventType.HOLD_FAST_FORWARD_START:
        next_state = InteractionState(PlaybackState.FAST_FORWARD, state.surface, event.playback_rate or 2.0, state.content_visit_open, state.media_episode)
        effects.append(ReducerEffect.SUSPEND_MEDIA_ANALYSIS)
    elif kind is EventType.HOLD_FAST_FORWARD_END:
        next_state = InteractionState(PlaybackState.PLAYING, state.surface, 1.0, state.content_visit_open, state.media_episode + 1)
        effects.extend((ReducerEffect.START_NEW_MEDIA_EPISODE, ReducerEffect.RESUME_MEDIA_ANALYSIS))
    elif kind is EventType.SPEED_ADJUST:
        next_state = InteractionState(
            state.playback,
            state.surface,
            event.playback_rate or state.playback_rate,
            state.content_visit_open,
            state.media_episode + 1,
        )
        effects.extend((ReducerEffect.START_NEW_MEDIA_EPISODE, ReducerEffect.RECORD_INTERFACE_CONTEXT))
    elif kind in CONTENT_SWITCH:
        next_state = InteractionState(PlaybackState.PLAYING, FocusSurface.FEED if kind in {EventType.RETURN_BACK, EventType.REFRESH_FEED} else FocusSurface.VIDEO, 1.0, True, state.media_episode + 1)
        effects.extend((ReducerEffect.CLOSE_CONTENT_VISIT, ReducerEffect.START_CONTENT_VISIT, ReducerEffect.RESUME_MEDIA_ANALYSIS))
    elif kind is EventType.BACKGROUND:
        next_state = InteractionState(PlaybackState.BACKGROUND, FocusSurface.NONE, state.playback_rate, state.content_visit_open, state.media_episode)
        effects.append(ReducerEffect.SUSPEND_MEDIA_ANALYSIS)
    elif kind is EventType.FOREGROUND:
        next_state = InteractionState(PlaybackState.PAUSED, FocusSurface.VIDEO, state.playback_rate, state.content_visit_open, state.media_episode)
        effects.append(ReducerEffect.RECORD_INTERFACE_CONTEXT)
    elif kind is EventType.OPEN_COMMENTS:
        next_state = InteractionState(state.playback, FocusSurface.COMMENTS, state.playback_rate, state.content_visit_open, state.media_episode)
        effects.append(ReducerEffect.RECORD_INTERFACE_CONTEXT)
    elif kind is EventType.CLOSE_COMMENTS:
        next_state = InteractionState(state.playback, FocusSurface.VIDEO, state.playback_rate, state.content_visit_open, state.media_episode)
        effects.append(ReducerEffect.RECORD_INTERFACE_CONTEXT)
    elif kind in {EventType.L1_PROMPT_OPENED, EventType.L2_EXPLORATION_OPENED, EventType.L3_GUIDED_PRACTICE_STARTED, EventType.L4_SELF_PRACTICE_STARTED}:
        effect = {
            EventType.L1_PROMPT_OPENED: ReducerEffect.OPEN_L1_PROMPT,
            EventType.L2_EXPLORATION_OPENED: ReducerEffect.OPEN_L2_EXPLORATION,
            EventType.L3_GUIDED_PRACTICE_STARTED: ReducerEffect.START_L3_GUIDED_PRACTICE,
            EventType.L4_SELF_PRACTICE_STARTED: ReducerEffect.START_L4_SELF_PRACTICE,
        }[kind]
        effects.append(effect)
    elif kind in ENGAGEMENT:
        effects.append(ReducerEffect.RECORD_ENGAGEMENT)
    else:
        effects.append(ReducerEffect.RECORD_INTERFACE_CONTEXT)
    return Transition(next_state, tuple(effects))
