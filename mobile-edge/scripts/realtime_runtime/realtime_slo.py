"""Fail-closed evidence for the narrowly defined realtime capability.

This module deliberately does not contain product latency defaults.  A run is
realtime only when a separately approved policy for the exact device-model
configuration is evaluated against a continuous *real-device* measurement.
Offline replay, unit-test fixtures and incomplete reports remain useful
diagnostics, but their capability status is always ``NOT_REALTIME``.
"""

from __future__ import annotations

from contextlib import closing
from dataclasses import asdict, dataclass
from enum import StrEnum
import hashlib
import json
import math
from pathlib import Path
import sqlite3
from typing import Any


class RealtimeInputSource(StrEnum):
    """Provenance of the media used for the measurement, not a quality score."""

    REAL_DEVICE_CONTINUOUS_STREAM = "REAL_DEVICE_CONTINUOUS_STREAM"
    REPLAY = "REPLAY"
    SIMULATION = "SIMULATION"
    UNVERIFIED = "UNVERIFIED"


class RealtimeStatus(StrEnum):
    REALTIME = "REALTIME"
    NOT_REALTIME = "NOT_REALTIME"


def _is_sha256(value: str | None) -> bool:
    if value is None or len(value) != 64:
        return False
    try:
        int(value, 16)
    except ValueError:
        return False
    return True


@dataclass(frozen=True)
class DeviceModelConfiguration:
    """All inputs that can materially change a device/model benchmark."""

    device_model: str
    android_api_level: int
    capture_build_hash: str
    pc_model: str
    model_id: str
    model_artifact_hash: str
    runtime_version: str

    def __post_init__(self) -> None:
        if not all((self.device_model, self.pc_model, self.model_id, self.runtime_version)):
            raise ValueError("device_model_configuration_identity_invalid")
        if self.android_api_level < 1:
            raise ValueError("device_model_configuration_android_api_invalid")
        if not _is_sha256(self.capture_build_hash) or not _is_sha256(self.model_artifact_hash):
            raise ValueError("device_model_configuration_hash_invalid")

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> "DeviceModelConfiguration":
        return cls(
            device_model=str(value["device_model"]),
            android_api_level=int(value["android_api_level"]),
            capture_build_hash=str(value["capture_build_hash"]),
            pc_model=str(value["pc_model"]),
            model_id=str(value["model_id"]),
            model_artifact_hash=str(value["model_artifact_hash"]),
            runtime_version=str(value["runtime_version"]),
        )


@dataclass(frozen=True)
class RealtimeServiceLevelPolicy:
    """Approved thresholds for exactly one supported device/model configuration."""

    policy_id: str
    configuration: DeviceModelConfiguration
    approved_benchmark_report_sha256: str
    minimum_continuous_input_ns: int
    minimum_samples: int
    maximum_p95_latency_ns: int
    maximum_latency_ns: int
    minimum_input_windows_per_second: float
    minimum_processed_windows_per_second: float
    maximum_queue_depth: int
    measurement_window_ns: int
    approved_overload_actions: tuple[str, ...]

    def __post_init__(self) -> None:
        if not self.policy_id:
            raise ValueError("realtime_slo_policy_id_missing")
        if not _is_sha256(self.approved_benchmark_report_sha256):
            raise ValueError("approved_benchmark_report_hash_invalid")
        if self.minimum_continuous_input_ns <= 0 or self.measurement_window_ns <= 0:
            raise ValueError("realtime_slo_duration_invalid")
        if self.minimum_samples <= 0:
            raise ValueError("realtime_slo_minimum_samples_invalid")
        if self.maximum_p95_latency_ns <= 0 or self.maximum_latency_ns <= 0:
            raise ValueError("realtime_slo_latency_threshold_invalid")
        if self.maximum_p95_latency_ns > self.maximum_latency_ns:
            raise ValueError("realtime_slo_p95_exceeds_maximum")
        if self.minimum_input_windows_per_second <= 0 or self.minimum_processed_windows_per_second <= 0:
            raise ValueError("realtime_slo_throughput_threshold_invalid")
        if self.maximum_queue_depth < 0:
            raise ValueError("realtime_slo_queue_threshold_invalid")
        if not self.approved_overload_actions or any(not value for value in self.approved_overload_actions):
            raise ValueError("approved_overload_actions_missing")
        if len(set(self.approved_overload_actions)) != len(self.approved_overload_actions):
            raise ValueError("approved_overload_actions_duplicate")

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> "RealtimeServiceLevelPolicy":
        return cls(
            policy_id=str(value["policy_id"]),
            configuration=DeviceModelConfiguration.from_dict(dict(value["configuration"])),
            approved_benchmark_report_sha256=str(value["approved_benchmark_report_sha256"]),
            minimum_continuous_input_ns=int(value["minimum_continuous_input_ns"]),
            minimum_samples=int(value["minimum_samples"]),
            maximum_p95_latency_ns=int(value["maximum_p95_latency_ns"]),
            maximum_latency_ns=int(value["maximum_latency_ns"]),
            minimum_input_windows_per_second=float(value["minimum_input_windows_per_second"]),
            minimum_processed_windows_per_second=float(value["minimum_processed_windows_per_second"]),
            maximum_queue_depth=int(value["maximum_queue_depth"]),
            measurement_window_ns=int(value["measurement_window_ns"]),
            approved_overload_actions=tuple(str(item) for item in value["approved_overload_actions"]),
        )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class RealtimeMeasurement:
    """Raw, configuration-bound measurement facts for one continuous stream."""

    input_source: RealtimeInputSource
    configuration: DeviceModelConfiguration
    raw_observation_log_sha256: str | None
    device_stream_attestation_sha256: str | None
    started_monotonic_ns: int
    ended_monotonic_ns: int
    input_window_count: int
    processed_window_count: int
    latency_samples_ns: tuple[int, ...]
    maximum_queue_depth: int | None
    overload_state: str | None
    overload_action: str | None
    continuous_input_verified: bool
    observed_continuous_input_ns: int | None

    def __post_init__(self) -> None:
        if self.started_monotonic_ns < 0 or self.ended_monotonic_ns <= self.started_monotonic_ns:
            raise ValueError("realtime_measurement_time_invalid")
        if self.input_window_count < 0 or self.processed_window_count < 0:
            raise ValueError("realtime_measurement_window_count_invalid")
        if any(item < 0 for item in self.latency_samples_ns):
            raise ValueError("realtime_measurement_latency_invalid")
        if self.maximum_queue_depth is not None and self.maximum_queue_depth < 0:
            raise ValueError("realtime_measurement_queue_invalid")
        if self.observed_continuous_input_ns is not None and self.observed_continuous_input_ns <= 0:
            raise ValueError("realtime_measurement_continuous_input_duration_invalid")

    @property
    def duration_ns(self) -> int:
        return self.ended_monotonic_ns - self.started_monotonic_ns

    def to_dict(self) -> dict[str, Any]:
        return {
            "input_source": self.input_source.value,
            "configuration": asdict(self.configuration),
            "raw_observation_log_sha256": self.raw_observation_log_sha256,
            "device_stream_attestation_sha256": self.device_stream_attestation_sha256,
            "started_monotonic_ns": self.started_monotonic_ns,
            "ended_monotonic_ns": self.ended_monotonic_ns,
            "input_window_count": self.input_window_count,
            "processed_window_count": self.processed_window_count,
            "latency_samples_ns": list(self.latency_samples_ns),
            "maximum_queue_depth": self.maximum_queue_depth,
            "overload_state": self.overload_state,
            "overload_action": self.overload_action,
            "continuous_input_verified": self.continuous_input_verified,
            "observed_continuous_input_ns": self.observed_continuous_input_ns,
        }


@dataclass(frozen=True)
class RealtimeMetrics:
    attested_device_stream_duration_ns: int
    observed_continuous_input_ns: int | None
    sample_count: int
    p95_latency_ns: int | None
    maximum_latency_ns: int | None
    input_windows_per_second: float
    processed_windows_per_second: float
    maximum_queue_depth: int | None
    overload_state: str | None
    overload_action: str | None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class RealtimeServiceLevelDecision:
    status: RealtimeStatus
    reasons: tuple[str, ...]
    metrics: RealtimeMetrics

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status.value,
            "reasons": list(self.reasons),
            "metrics": self.metrics.to_dict(),
        }


def _percentile_95(samples: tuple[int, ...]) -> int | None:
    """Nearest-rank percentile: no interpolation can hide an observed tail."""
    if not samples:
        return None
    ordered = sorted(samples)
    return ordered[math.ceil(len(ordered) * 0.95) - 1]


def _metrics(measurement: RealtimeMeasurement) -> RealtimeMetrics:
    duration_ns = measurement.observed_continuous_input_ns or measurement.duration_ns
    seconds = duration_ns / 1_000_000_000
    return RealtimeMetrics(
        attested_device_stream_duration_ns=measurement.duration_ns,
        observed_continuous_input_ns=measurement.observed_continuous_input_ns,
        sample_count=len(measurement.latency_samples_ns),
        p95_latency_ns=_percentile_95(measurement.latency_samples_ns),
        maximum_latency_ns=max(measurement.latency_samples_ns, default=None),
        input_windows_per_second=measurement.input_window_count / seconds,
        processed_windows_per_second=measurement.processed_window_count / seconds,
        maximum_queue_depth=measurement.maximum_queue_depth,
        overload_state=measurement.overload_state,
        overload_action=measurement.overload_action,
    )


def evaluate_realtime_service_level(
    policy: RealtimeServiceLevelPolicy | None,
    measurement: RealtimeMeasurement,
) -> RealtimeServiceLevelDecision:
    """Evaluate all gates and report every failure; no partial pass is realtime."""
    metrics = _metrics(measurement)
    if policy is None:
        return RealtimeServiceLevelDecision(RealtimeStatus.NOT_REALTIME, ("policy_missing",), metrics)

    reasons: list[str] = []
    if measurement.input_source is not RealtimeInputSource.REAL_DEVICE_CONTINUOUS_STREAM:
        reasons.append("input_source_not_real_device")
    if measurement.configuration != policy.configuration:
        reasons.append("device_model_configuration_mismatch")
    if not _is_sha256(measurement.raw_observation_log_sha256):
        reasons.append("raw_observation_log_missing")
    if not _is_sha256(measurement.device_stream_attestation_sha256):
        reasons.append("device_stream_attestation_missing")
    if metrics.attested_device_stream_duration_ns < policy.minimum_continuous_input_ns:
        reasons.append("attested_device_stream_duration_below_policy")
    if not measurement.continuous_input_verified or metrics.observed_continuous_input_ns is None:
        reasons.append("continuous_input_not_proven")
    elif metrics.observed_continuous_input_ns < policy.minimum_continuous_input_ns:
        reasons.append("continuous_input_duration_below_policy")
    if metrics.observed_continuous_input_ns is None or metrics.observed_continuous_input_ns < policy.measurement_window_ns:
        reasons.append("measurement_window_below_policy")
    if metrics.sample_count < policy.minimum_samples:
        reasons.append("sample_count_below_policy")
    if metrics.p95_latency_ns is None:
        reasons.append("latency_samples_missing")
    elif metrics.p95_latency_ns > policy.maximum_p95_latency_ns:
        reasons.append("p95_latency_exceeds_policy")
    if metrics.maximum_latency_ns is None:
        reasons.append("maximum_latency_missing")
    elif metrics.maximum_latency_ns > policy.maximum_latency_ns:
        reasons.append("maximum_latency_exceeds_policy")
    if metrics.input_windows_per_second < policy.minimum_input_windows_per_second:
        reasons.append("input_throughput_below_policy")
    if metrics.processed_windows_per_second < policy.minimum_processed_windows_per_second:
        reasons.append("processed_throughput_below_policy")
    if metrics.maximum_queue_depth is None:
        reasons.append("queue_depth_missing")
    elif metrics.maximum_queue_depth > policy.maximum_queue_depth:
        reasons.append("queue_depth_exceeds_policy")
    if not metrics.overload_state:
        reasons.append("overload_state_missing")
    if not metrics.overload_action:
        reasons.append("overload_action_missing")
    elif metrics.overload_state != "NORMAL" and metrics.overload_action not in policy.approved_overload_actions:
        reasons.append("overload_action_unapproved")

    return RealtimeServiceLevelDecision(
        RealtimeStatus.REALTIME if not reasons else RealtimeStatus.NOT_REALTIME,
        tuple(reasons),
        metrics,
    )


def load_realtime_service_level_policy(path: Path) -> RealtimeServiceLevelPolicy:
    """Load explicit approval data. Missing files are handled by the caller as no policy."""
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("realtime_slo_policy_json_invalid")
    return RealtimeServiceLevelPolicy.from_dict(value)


def sha256_file(path: Path) -> str:
    """Hash an original observation artifact without rewriting or normalizing it."""
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _sha256_artifact_bundle(paths: tuple[Path, ...], *, declared_device_log_hash: str) -> str:
    """Bind immutable runtime artifacts and the device-declared raw-log hash.

    The mobile raw log can remain on the phone under its retention policy, so
    the PC report records its declared digest without copying its content into
    a desktop artifact.  The PC-side ledger and progress log are hashed in
    their original byte form.
    """
    digest = hashlib.sha256()
    for path in paths:
        if not path.is_file():
            raise ValueError(f"realtime_observation_artifact_missing:{path.name}")
        digest.update(path.name.encode("utf-8"))
        digest.update(bytes.fromhex(sha256_file(path)))
    digest.update(b"device_raw_log_sha256")
    digest.update(bytes.fromhex(declared_device_log_hash))
    return digest.hexdigest()


def _load_device_stream_attestation(path: Path, *, expected_capture_session_id: str) -> tuple[RealtimeInputSource, DeviceModelConfiguration, int, int, str]:
    if not path.is_file():
        raise ValueError("device_stream_attestation_missing")
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(value, dict):
            raise ValueError("device_stream_attestation_json_invalid")
        if str(value["capture_session_id"]) != expected_capture_session_id:
            raise ValueError("device_stream_attestation_session_mismatch")
        source = RealtimeInputSource(str(value["input_source"]))
        configuration = DeviceModelConfiguration.from_dict(dict(value["configuration"]))
        started = int(value["stream_started_monotonic_ns"])
        ended = int(value["stream_ended_monotonic_ns"])
        raw_device_log_hash = str(value["raw_device_log_sha256"])
    except KeyError as error:
        raise ValueError("device_stream_attestation_field_missing") from error
    except json.JSONDecodeError as error:
        raise ValueError("device_stream_attestation_json_invalid") from error
    except ValueError:
        raise
    if started < 0 or ended <= started:
        raise ValueError("device_stream_attestation_time_invalid")
    if not _is_sha256(raw_device_log_hash):
        raise ValueError("device_stream_attestation_raw_log_hash_invalid")
    return source, configuration, started, ended, raw_device_log_hash


def _maximum_queue_depth_from_progress(path: Path) -> int | None:
    if not path.is_file():
        raise ValueError("realtime_progress_log_missing")
    depths: list[int] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line:
            continue
        try:
            event = json.loads(line)
        except json.JSONDecodeError as error:
            raise ValueError("realtime_progress_log_invalid") from error
        if not isinstance(event, dict) or "queue_depth" not in event:
            continue
        depth = event["queue_depth"]
        if not isinstance(depth, int) or depth < 0:
            raise ValueError("realtime_progress_queue_invalid")
        depths.append(depth)
    return max(depths, default=None)


def measurement_from_e2e_artifacts(
    *,
    ledger_path: Path,
    progress_path: Path,
    device_stream_attestation_path: Path,
    expected_capture_session_id: str,
) -> RealtimeMeasurement:
    """Build a measurement from original PC artifacts and a bound phone receipt.

    This is intentionally a parser, not an emulator.  If a run did not emit
    the phone proof or raw PC artifacts, the caller must report
    ``NOT_REALTIME`` rather than manufacture zero-valued metrics.
    """
    source, configuration, started, ended, raw_device_log_hash = _load_device_stream_attestation(
        device_stream_attestation_path, expected_capture_session_id=expected_capture_session_id
    )
    maximum_queue_depth = _maximum_queue_depth_from_progress(progress_path)
    if not ledger_path.is_file():
        raise ValueError("realtime_ledger_missing")
    try:
        with closing(sqlite3.connect(ledger_path)) as connection:
            fragment_rows = connection.execute(
                """
                SELECT pc_arrival_first_ns, pc_sealed_ns, start_pts_ns, end_pts_ns, gap_before
                FROM fragments
                ORDER BY start_pts_ns, end_pts_ns
                """
            ).fetchall()
            input_window_count = len(fragment_rows)
            latency_rows = connection.execute(
                """
                SELECT fused_at_ns - created_ns AS latency_ns
                FROM semantic_windows
                WHERE fused_at_ns IS NOT NULL AND created_ns > 0 AND fused_at_ns >= created_ns
                ORDER BY fused_at_ns
                """
            ).fetchall()
    except sqlite3.Error as error:
        raise ValueError("realtime_ledger_schema_invalid") from error
    latencies = tuple(int(row[0]) for row in latency_rows)
    observed_continuous_input_ns: int | None = None
    continuous_input_verified = bool(fragment_rows)
    if fragment_rows:
        observed_continuous_input_ns = int(fragment_rows[-1][1]) - int(fragment_rows[0][0])
        previous_end_pts: int | None = None
        for row in fragment_rows:
            start_pts, end_pts, gap_before = int(row[2]), int(row[3]), int(row[4])
            if end_pts <= start_pts or gap_before != 0 or (previous_end_pts is not None and start_pts != previous_end_pts):
                continuous_input_verified = False
                break
            previous_end_pts = end_pts
        if observed_continuous_input_ns <= 0:
            observed_continuous_input_ns = None
            continuous_input_verified = False
    # There is no implemented overload governor yet.  A measured queue is
    # therefore only "normal" while no overload was observed; when a later
    # governor emits an overload action, its event must replace this record.
    overload_state = "NORMAL" if maximum_queue_depth is not None else None
    overload_action = "NONE_REQUIRED" if maximum_queue_depth is not None else None
    return RealtimeMeasurement(
        input_source=source,
        configuration=configuration,
        raw_observation_log_sha256=_sha256_artifact_bundle(
            (ledger_path, progress_path), declared_device_log_hash=raw_device_log_hash
        ),
        device_stream_attestation_sha256=sha256_file(device_stream_attestation_path),
        started_monotonic_ns=started,
        ended_monotonic_ns=ended,
        input_window_count=input_window_count,
        processed_window_count=len(latencies),
        latency_samples_ns=latencies,
        maximum_queue_depth=maximum_queue_depth,
        overload_state=overload_state,
        overload_action=overload_action,
        continuous_input_verified=continuous_input_verified,
        observed_continuous_input_ns=observed_continuous_input_ns,
    )
