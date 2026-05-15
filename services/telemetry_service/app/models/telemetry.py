from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, Float, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class TelemetryRecord(Base):
    __tablename__ = "telemetry"

    id: Mapped[int] = mapped_column(primary_key=True)
    device_id: Mapped[str] = mapped_column(String(50), default="bpna-01")
    battery: Mapped[float] = mapped_column(Float, nullable=False)
    temperature: Mapped[float | None] = mapped_column(Float, nullable=True)
    free_heap: Mapped[int | None] = mapped_column(Integer, nullable=True)
    uptime: Mapped[int | None] = mapped_column(Integer, nullable=True)
    cpu_load: Mapped[float | None] = mapped_column(Float, nullable=True)
    wifi_connected: Mapped[bool] = mapped_column(Boolean, default=True)
    wifi_rssi_dbm: Mapped[int | None] = mapped_column(Integer, nullable=True)
    ping_ms: Mapped[float | None] = mapped_column(Float, nullable=True)
    ping_ok: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
    )
