from pydantic import BaseModel


class MeasurementIn(BaseModel):
    type: str = "wifi_measurement"
    device_id: str = "bpna-01"
    x: int = 0
    y: int = 0
    rssi: int
    step_cm: int = 100
    session_id: str | None = None
