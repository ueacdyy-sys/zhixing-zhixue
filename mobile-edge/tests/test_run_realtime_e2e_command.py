from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

from scripts.run_realtime_e2e import (  # noqa: E402
    LaneProfile,
    V2L0ProjectionConfig,
    build_pipeline_command,
    build_worker_command,
    _load_v2_l0_projection_config,
)


def test_pipeline_command_preserves_capture_session_id_instead_of_output_directory_name() -> None:
    command = build_pipeline_command(
        source="rtsp://127.0.0.1:8554/screen",
        capture_session_id="capture-session-from-gateway",
        capture_generation=8,
        output_dir=Path("C:/captures/unrelated-output-folder"),
        duration_seconds=0.0,
        fragments_per_window=2,
        window_hop_fragments=2,
        stop_signal_file=None,
        analysis_route_lease_json=None,
        transition_events=None,
        audio_telemetry_journal=Path("C:/captures/capture.audio-l0.jsonl"),
    )

    assert command[command.index("--session-id") + 1] == "capture-session-from-gateway"
    assert command[command.index("--capture-generation") + 1] == "8"
    # The child command is Windows-visible, so its separators are an
    # implementation detail.  The contract is that the companion L0 journal
    # is forwarded with the same filename.
    assert Path(command[command.index("--audio-telemetry-journal") + 1]).name == "capture.audio-l0.jsonl"


def test_v2_l0_worker_command_binds_projection_to_the_authorized_route_scope() -> None:
    config = V2L0ProjectionConfig(
        semantic_ledger_path=Path("C:/captures/semantic_l0.sqlite"),
        route_ledger_path=Path("C:/captures/analysis_route.sqlite"),
        learner_id="learner-1",
        capture_consent_id="consent-1",
        consent_generation=3,
        route_lease_id="route-1",
        route_epoch=5,
        owner_endpoint_id="pc-1",
    )

    command = build_worker_command(
        profile=LaneProfile("OCR", Path("C:/python/python.exe")),
        ledger=Path("C:/captures/evidence_ledger.sqlite"),
        capture_root=Path("C:/captures"),
        artifact_root=Path("C:/captures/artifacts"),
        duration_seconds=0.0,
        projection=config,
    )

    assert command[command.index("--v2-learner-id") + 1] == "learner-1"
    assert command[command.index("--v2-capture-consent-id") + 1] == "consent-1"
    assert command[command.index("--v2-consent-generation") + 1] == "3"
    assert command[command.index("--v2-route-lease-id") + 1] == "route-1"
    assert command[command.index("--v2-route-epoch") + 1] == "5"
    assert command[command.index("--v2-owner-endpoint-id") + 1] == "pc-1"
    assert Path(command[command.index("--v2-semantic-ledger") + 1]).name == "semantic_l0.sqlite"
    assert Path(command[command.index("--v2-route-ledger") + 1]).name == "analysis_route.sqlite"


def _pc_route_lease_payload(*, session_id: str) -> dict[str, object]:
    return {
        "lease_id": "route-1",
        "learner_id": "learner-1",
        "session_id": session_id,
        "capture_consent_id": "consent-1",
        "consent_generation": 3,
        "route_epoch": 5,
        "state": "PC_LOCAL_ACTIVE",
        "owner_endpoint_id": "pc-1",
        "opened_receipt_hash": "a" * 64,
        "student_confirmation_hash": "b" * 64,
        "issued_elapsed_ns": 10,
        "last_renewed_elapsed_ns": 20,
        "expires_elapsed_ns": 30,
    }


def test_v2_l0_projection_is_blocked_until_media_transport_security_is_implemented(tmp_path: Path) -> None:
    lease_path = tmp_path / "route.json"
    lease_path.write_text(json.dumps(_pc_route_lease_payload(session_id="capture-1")), encoding="utf-8")

    with pytest.raises(ValueError, match="v2_media_security_transport_unavailable"):
        _load_v2_l0_projection_config(
            lease_path,
            output_dir=tmp_path / "output",
            capture_session_id="capture-1",
        )


def test_v2_l0_projection_rejects_a_route_lease_for_another_capture_session(tmp_path: Path) -> None:
    lease_path = tmp_path / "route.json"
    lease_path.write_text(json.dumps(_pc_route_lease_payload(session_id="capture-other")), encoding="utf-8")

    with pytest.raises(ValueError, match="analysis_route_lease_session_mismatch"):
        _load_v2_l0_projection_config(
            lease_path,
            output_dir=tmp_path / "output",
            capture_session_id="capture-1",
        )


def test_v2_l0_projection_rejects_a_route_lease_with_a_missing_learner_identity(tmp_path: Path) -> None:
    lease_path = tmp_path / "route.json"
    payload = _pc_route_lease_payload(session_id="capture-1")
    payload["learner_id"] = None
    lease_path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(ValueError, match="analysis_route_lease_unusable"):
        _load_v2_l0_projection_config(
            lease_path,
            output_dir=tmp_path / "output",
            capture_session_id="capture-1",
        )
