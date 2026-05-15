from fastapi import APIRouter, Depends, HTTPException, Query, WebSocket
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth_client import require_user, validate_ws_token
from app.core.database import get_db
from app.schemas.wifi import MeasurementIn
from app.services import state
from app.services.scan_service import start_scan as start_wifi_scan
from app.services.scan_service import stop_scan as stop_wifi_scan
from app.services.websocket_service import register_wifi_viewer
from app.services.wifi_service import (
    build_heatmap,
    clear_measurements as clear_wifi_measurements,
    get_measurements,
    get_saved_heatmap,
    get_saved_heatmaps,
    save_heatmap_snapshot,
    save_measurement,
)


router = APIRouter()


@router.post("/internal/measurements")
async def save_measurement_endpoint(
    data: MeasurementIn,
    db: AsyncSession = Depends(get_db),
):
    point = await save_measurement(db, data)
    return {"status": "saved", "id": point.id}


@router.websocket("/ws/measurements")
async def measurements_ws(websocket: WebSocket, token: str = Query(...)):
    if not await validate_ws_token(token):
        await websocket.close(code=1008)
        return
    await register_wifi_viewer(websocket)


@router.get("/measurements")
async def measurements(
    limit: int = 500,
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(require_user),
):
    rows = await get_measurements(db, limit)
    return [
        {
            "x": item.x,
            "y": item.y,
            "rssi": item.rssi,
            "step_cm": item.step_cm,
            "created_at": item.created_at.isoformat(),
        }
        for item in rows
    ]


@router.get("/heatmap")
async def heatmap(
    width_cells: int = 10,
    height_cells: int = 10,
    step_cm: int = 100,
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(require_user),
):
    return await build_heatmap(db, width_cells, height_cells, step_cm)


@router.get("/track")
async def get_track(user: dict = Depends(require_user)):
    return {"track": state.drone_track}


@router.delete("/track")
async def clear_track(user: dict = Depends(require_user)):
    state.drone_track.clear()
    return {"status": "cleared"}


@router.post("/start")
async def start_scan(
    width: int = 10,
    height: int = 10,
    step_cm: int = 100,
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(require_user),
):
    return await start_wifi_scan(db, width, height, step_cm)


@router.post("/stop")
async def stop_scan(user: dict = Depends(require_user)):
    return await stop_wifi_scan()


@router.post("/save")
async def save_heatmap(
    name: str,
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(require_user),
):
    saved = await save_heatmap_snapshot(db, name)
    return {"status": "saved", "id": saved.id, "name": name}


@router.get("/saved")
async def saved_heatmaps(
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(require_user),
):
    rows = await get_saved_heatmaps(db)
    return [
        {"id": item.id, "name": item.name, "created_at": item.created_at.isoformat()}
        for item in rows
    ]


@router.get("/saved/{heatmap_id}")
async def saved_heatmap(
    heatmap_id: int,
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(require_user),
):
    item = await get_saved_heatmap(db, heatmap_id)
    if item is None:
        raise HTTPException(status_code=404, detail="Heatmap not found")
    return {
        "id": item.id,
        "name": item.name,
        "data": item.data,
        "created_at": item.created_at.isoformat(),
    }


@router.delete("/measurements")
async def clear_measurements(
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(require_user),
):
    await clear_wifi_measurements(db)
    return {"status": "cleared"}
