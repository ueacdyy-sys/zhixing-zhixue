import pytest

from zhixingzhixue_hub.devices.connection_contract import ConnectionContractError, validate_connection


def valid_connection() -> dict[str, object]:
    return {
        "connection_id": "con-001",
        "session_id": "ses-001",
        "device_id": "glasses-001",
        "device_type": "glasses",
        "transport": "lan",
        "data_route": "pc_direct",
        "status": "connected",
        "capabilities": ["first_person_video", "time_sync"],
        "clock_offset_ms": -8,
        "quality": "usable",
    }


def test_connection_contract_accepts_phone_controlled_glasses_with_pc_direct_video_route() -> None:
    connection = validate_connection(valid_connection())

    assert connection["device_type"] == "glasses"
    assert connection["data_route"] == "pc_direct"
    assert connection["clock_offset_ms"] == -8


@pytest.mark.parametrize(
    "field",
    ["session_id", "device_id", "transport", "data_route", "capabilities", "clock_offset_ms", "quality"],
)
def test_connection_contract_rejects_missing_required_hardware_state(field: str) -> None:
    connection = valid_connection()
    connection.pop(field)

    with pytest.raises(ConnectionContractError, match=field):
        validate_connection(connection)


def test_connection_contract_rejects_unknown_transport() -> None:
    connection = valid_connection()
    connection["transport"] = "vendor_cloud_tunnel"

    with pytest.raises(ConnectionContractError, match="transport"):
        validate_connection(connection)
