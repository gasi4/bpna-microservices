import io
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth_client import require_user
from app.core.database import get_db
from app.services.export_service import export_to_csv, export_to_json
from app.services.telemetry_service import get_records


router = APIRouter()


@router.get("/summary")
async def summary(
    device_id: str = "bpna-01",
    hours: int = 24,
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(require_user),
):
    since = datetime.now(timezone.utc) - timedelta(hours=hours)
    records = await get_records(db, device_id, since, None, 10_000)
    if not records:
        return {"device_id": device_id, "total_records": 0}

    batteries = [record.battery for record in records]
    temps = [record.temperature for record in records if record.temperature is not None]
    return {
        "device_id": device_id,
        "period_hours": hours,
        "total_records": len(records),
        "battery_start": batteries[0],
        "battery_end": batteries[-1],
        "battery_used": round(batteries[0] - batteries[-1], 1),
        "temp_avg": round(sum(temps) / len(temps), 1) if temps else None,
        "temp_max": max(temps) if temps else None,
    }


@router.get("/export/csv")
async def export_csv(
    device_id: str = Query("bpna-01"),
    from_dt: datetime | None = Query(None),
    to_dt: datetime | None = Query(None),
    limit: int = Query(1000),
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(require_user),
):
    records = await get_records(db, device_id, from_dt, to_dt, limit)
    return StreamingResponse(
        io.StringIO(export_to_csv(records)),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename=session_{device_id}.csv"},
    )


@router.get("/export/json")
async def export_json_endpoint(
    device_id: str = Query("bpna-01"),
    from_dt: datetime | None = Query(None),
    to_dt: datetime | None = Query(None),
    limit: int = Query(1000),
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(require_user),
):
    records = await get_records(db, device_id, from_dt, to_dt, limit)
    return StreamingResponse(
        io.StringIO(export_to_json(records)),
        media_type="application/json",
        headers={"Content-Disposition": f"attachment; filename=session_{device_id}.json"},
    )
