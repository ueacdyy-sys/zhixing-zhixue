from zhixingzhixue_hub.adapters.android_adb import build_phone_connection


def test_authorized_android_adb_probe_maps_to_replaceable_phone_connection_contract() -> None:
    connection = build_phone_connection(
        session_id="ses-phone-live-001",
        serial="NBLDU20C09022238",
        transport="usb",
        model="ANG-AN00",
        android_version="12",
        screen_stream_service_available=True,
        clock_offset_ms=12,
    )

    assert connection["device_id"] == "android:NBLDU20C09022238"
    assert connection["device_type"] == "phone"
    assert connection["transport"] == "usb"
    assert connection["data_route"] == "local_only"
    assert connection["status"] == "connected"
    assert connection["capabilities"] == [
        "adb_authorized",
        "android_12",
        "model_ANG-AN00",
        "screen_stream_service_available",
    ]
