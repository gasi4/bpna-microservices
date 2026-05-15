from datetime import datetime

from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.telemetry import TelemetryRecord
from app.schemas.telemetry import TelemetryData


async def save_telemetry(
    db: AsyncSession,
    data: TelemetryData,
) -> TelemetryRecord:
    record = TelemetryRecord(**data.model_dump())
    db.add(record)
    await db.commit()
    await db.refresh(record)
    return record


async def get_history(
    db: AsyncSession,
    device_id: str = "bpna-01",
    limit: int = 100,
) -> list[TelemetryRecord]:
    result = await db.execute(
        select(TelemetryRecord)
        .where(TelemetryRecord.device_id == device_id)
        .order_by(desc(TelemetryRecord.created_at))
        .limit(limit)
    )
    return list(result.scalars().all())


async def get_records(
    db: AsyncSession,
    device_id: str,
    from_dt: datetime | None,
    to_dt: datetime | None,
    limit: int,
) -> list[TelemetryRecord]:
    query = select(TelemetryRecord).where(TelemetryRecord.device_id == device_id)
    if from_dt:
        query = query.where(TelemetryRecord.created_at >= from_dt)
    if to_dt:
        query = query.where(TelemetryRecord.created_at <= to_dt)

    result = await db.execute(query.order_by(TelemetryRecord.created_at).limit(limit))
    return list(result.scalars().all())
