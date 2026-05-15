from fastapi import APIRouter, Depends, HTTPException, Query, WebSocket
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth_client import require_user, validate_ws_token
from app.core.database import get_db
from app.schemas.wifi import MeasurementIn
from app.services.scan_service import (
    get_scan_status_payload,
    process_scan_step,
    set_scan_mode,
    start_scan as start_wifi_scan,
    stop_scan as stop_wifi_scan,
)
from app.services.state import get_device_state as get_scan_state
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


def normalize_device_id(device_id: str | None) -> str:
    return str(device_id or 'bpna-01')


@router.post('/internal/measurements')
async def save_measurement_endpoint(
    data: MeasurementIn,
    db: AsyncSession = Depends(get_db),
):
    point = await save_measurement(db, data)
    return {'status': 'saved', 'id': point.id}


@router.websocket('/ws/measurements')
async def measurements_ws(
    websocket: WebSocket,
    token: str = Query(...),
    device_id: str = Query(default='bpna-01'),
):
    if not await validate_ws_token(token):
        await websocket.close(code=1008)
        return
    await register_wifi_viewer(websocket, normalize_device_id(device_id))


@router.get('/measurements')
async def measurements(
    device_id: str = 'bpna-01',
    limit: int = 500,
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(require_user),
):
    normalized = normalize_device_id(device_id)
    rows = await get_measurements(db, normalized, limit)
    return [
        {
            'device_id': item.device_id,
            'x': item.x,
            'y': item.y,
            'rssi': item.rssi,
            'step_cm': item.step_cm,
            'created_at': item.created_at.isoformat(),
        }
        for item in rows
    ]


@router.get('/heatmap')
async def heatmap(
    device_id: str = 'bpna-01',
    width_cells: int = 10,
    height_cells: int = 10,
    step_cm: int = 100,
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(require_user),
):
    return await build_heatmap(db, normalize_device_id(device_id), width_cells, height_cells, step_cm)


@router.get('/track')
async def get_track(device_id: str = 'bpna-01', user: dict = Depends(require_user)):
    state = get_scan_state(normalize_device_id(device_id))
    return {'device_id': normalize_device_id(device_id), 'track': state.drone_track}


@router.get('/status')
async def scan_status(device_id: str = 'bpna-01', user: dict = Depends(require_user)):
    return get_scan_status_payload(normalize_device_id(device_id))


@router.delete('/track')
async def clear_track(device_id: str = 'bpna-01', user: dict = Depends(require_user)):
    state = get_scan_state(normalize_device_id(device_id))
    state.drone_track.clear()
    return {'status': 'cleared'}


@router.post('/start')
async def start_scan(
    device_id: str = 'bpna-01',
    width: int = 10,
    height: int = 10,
    step_cm: int = 100,
    mode: str = 'manual',
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(require_user),
):
    mode = mode if mode in {'manual', 'autopilot'} else 'manual'
    return await start_wifi_scan(db, normalize_device_id(device_id), width, height, step_cm, mode)


@router.post('/mode')
async def update_scan_mode(
    device_id: str = 'bpna-01',
    mode: str = 'manual',
    user: dict = Depends(require_user),
):
    mode = mode if mode in {'manual', 'autopilot'} else 'manual'
    return await set_scan_mode(normalize_device_id(device_id), mode)


@router.post('/stop')
async def stop_scan(device_id: str = 'bpna-01', user: dict = Depends(require_user)):
    return await stop_wifi_scan(normalize_device_id(device_id))


@router.post('/internal/step')
async def internal_step(
    data: dict,
    db: AsyncSession = Depends(get_db),
):
    command = str(data.get('command') or '')
    device_id = normalize_device_id(data.get('device_id'))
    return await process_scan_step(db, device_id, command, source='manual')


@router.post('/save')
async def save_heatmap(
    name: str,
    device_id: str = 'bpna-01',
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(require_user),
):
    saved = await save_heatmap_snapshot(db, name, normalize_device_id(device_id))
    return {'status': 'saved', 'id': saved.id, 'name': name}


@router.get('/saved')
async def saved_heatmaps(
    device_id: str = 'bpna-01',
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(require_user),
):
    rows = await get_saved_heatmaps(db, normalize_device_id(device_id))
    return [
        {'id': item.id, 'device_id': item.device_id, 'name': item.name, 'created_at': item.created_at.isoformat()}
        for item in rows
    ]


@router.get('/saved/{heatmap_id}')
async def saved_heatmap(
    heatmap_id: int,
    device_id: str = 'bpna-01',
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(require_user),
):
    item = await get_saved_heatmap(db, heatmap_id, normalize_device_id(device_id))
    if item is None:
        raise HTTPException(status_code=404, detail='Heatmap not found')
    return {
        'id': item.id,
        'device_id': item.device_id,
        'name': item.name,
        'data': item.data,
        'created_at': item.created_at.isoformat(),
    }


@router.delete('/measurements')
async def clear_measurements(
    device_id: str = 'bpna-01',
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(require_user),
):
    await clear_wifi_measurements(db, normalize_device_id(device_id))
    return {'status': 'cleared'}
