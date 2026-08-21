"""Capture-mode rules shared by the phone control plane and paired-PC gateway.

This module deliberately decides only whether a *currently authorized*
capture session may emit media to the PC.  It never treats a content switch,
an app switch, or a transport interruption as a request to delete historical
evidence.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class CaptureMode(StrEnum):
    FULL_CONTINUOUS = "FULL_CONTINUOUS"
    SELECTED_APPS = "SELECTED_APPS"


class CaptureOutputState(StrEnum):
    STREAMING_ALLOWED = "STREAMING_ALLOWED"
    STREAMING_BLOCKED = "STREAMING_BLOCKED"


@dataclass(frozen=True)
class CaptureOutputDecision:
    output_state: CaptureOutputState
    reason: str


@dataclass(frozen=True)
class CaptureInterruptionOutcome:
    session_state: str
    reason: str
    preserve_completed_evidence: bool
    mark_open_window_incomplete: bool


@dataclass(frozen=True)
class CaptureSessionPolicy:
    mode: CaptureMode
    selected_packages: tuple[str, ...]

    @classmethod
    def create(cls, mode: CaptureMode | str, selected_packages: tuple[str, ...]) -> "CaptureSessionPolicy":
        normalized_mode = CaptureMode(mode)
        normalized_packages = tuple(item.strip() for item in selected_packages)
        if any(not item for item in normalized_packages):
            raise ValueError("selected_app_package_blank")
        if len(set(normalized_packages)) != len(normalized_packages):
            raise ValueError("selected_app_packages_must_be_unique")
        if normalized_mode is CaptureMode.SELECTED_APPS and not normalized_packages:
            raise ValueError("selected_apps_requires_packages")
        if normalized_mode is CaptureMode.FULL_CONTINUOUS and normalized_packages:
            raise ValueError("full_continuous_disallows_selected_packages")
        return cls(mode=normalized_mode, selected_packages=normalized_packages)

    def decide(self, foreground_package: str | None) -> CaptureOutputDecision:
        if self.mode is CaptureMode.FULL_CONTINUOUS:
            return CaptureOutputDecision(CaptureOutputState.STREAMING_ALLOWED, "FULL_CONTINUOUS")
        if foreground_package is not None and foreground_package in self.selected_packages:
            return CaptureOutputDecision(CaptureOutputState.STREAMING_ALLOWED, "FOREGROUND_APP_SELECTED")
        return CaptureOutputDecision(CaptureOutputState.STREAMING_BLOCKED, "FOREGROUND_APP_NOT_SELECTED")

    @staticmethod
    def interruption_outcome(reason: str) -> CaptureInterruptionOutcome:
        if not reason:
            raise ValueError("capture_interruption_reason_required")
        return CaptureInterruptionOutcome(
            session_state="INTERRUPTED",
            reason=reason,
            preserve_completed_evidence=True,
            mark_open_window_incomplete=True,
        )
