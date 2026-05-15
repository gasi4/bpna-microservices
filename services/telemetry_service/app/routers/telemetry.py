from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth_client import require_user
from app.core.database import get_db
from app.schemas.telemetry import TelemetryData, TelemetryResponse
from app.services.telemetry_service import get_history, save_telemetry


router = APIRouter()


@router.post("/internal/telemetry", response_model=TelemetryResponse)
async def save_telemetry_endpoint(
    data: TelemetryData,
    db: AsyncSession = Depends(get_db),
):
    return await save_telemetry(db, data)


@router.get("/history", response_model=list[TelemetryResponse])
async def history(
    device_id: str = "bpna-01",
    limit: int = 100,
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(require_user),
):
    return await get_history(db, device_id=device_id, limit=limit)
