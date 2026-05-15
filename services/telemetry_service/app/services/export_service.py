import csv
import io
import json

from app.models.telemetry import TelemetryRecord
from app.schemas.telemetry import TelemetryResponse


CSV_COLUMNS = [
    "id",
    "device_id",
    "battery",
    "temperature",
    "free_heap",
    "uptime",
    "cpu_load",
    "wifi_connected",
    "wifi_rssi_dbm",
    "ping_ms",
    "ping_ok",
    "created_at",
]


def export_to_csv(records: list[TelemetryRecord]) -> str:
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(CSV_COLUMNS)

    for record in records:
        writer.writerow(
            [
                record.id,
                record.device_id,
                record.battery,
                record.temperature,
                record.free_heap,
                record.uptime,
                record.cpu_load,
                record.wifi_connected,
                record.wifi_rssi_dbm,
                record.ping_ms,
                record.ping_ok,
                record.created_at,
            ]
        )

    return output.getvalue()


def export_to_json(records: list[TelemetryRecord]) -> str:
    data = [
        TelemetryResponse.model_validate(record).model_dump(mode="json")
        for record in records
    ]
    return json.dumps(data, ensure_ascii=False, indent=2)
