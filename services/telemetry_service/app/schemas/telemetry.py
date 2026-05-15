from datetime import datetime

from pydantic import BaseModel, Field


class TelemetryData(BaseModel):
    device_id: str = "bpna-01"
    battery: float = Field(..., ge=0, le=100)
    temperature: float | None = None
    free_heap: int | None = None
    uptime: int | None = None
    cpu_load: float | None = Field(None, ge=0, le=100)
    wifi_connected: bool = True
    wifi_rssi_dbm: int | None = None
    ping_ms: float | None = None
    ping_ok: bool = False


class TelemetryResponse(TelemetryData):
    id: int
    created_at: datetime

    model_config = {"from_attributes": True}
