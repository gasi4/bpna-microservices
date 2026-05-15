from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.wifi import SavedHeatmap, WiFiMeasurement
from app.schemas.wifi import MeasurementIn
from app.services.heatmap_service import interpolate_heatmap
from app.services.websocket_service import broadcast_measurement


async def save_measurement(db: AsyncSession, data: MeasurementIn) -> WiFiMeasurement:
    point = WiFiMeasurement(
        x=data.x,
        y=data.y,
        rssi=data.rssi,
        step_cm=data.step_cm,
        session_id=data.session_id,
    )
    db.add(point)
    await db.commit()
    await db.refresh(point)

    payload = {
        'type': 'wifi_measurement',
        **data.model_dump(),
        'created_at': point.created_at.isoformat(),
    }
    await broadcast_measurement(payload)
    return point


async def save_measurement_payload(db: AsyncSession, payload: dict) -> WiFiMeasurement:
    data = MeasurementIn(**payload)
    return await save_measurement(db, data)


async def get_measurements(db: AsyncSession, limit: int = 500) -> list[WiFiMeasurement]:
    result = await db.execute(
        select(WiFiMeasurement).order_by(WiFiMeasurement.created_at.desc()).limit(limit)
    )
    return list(result.scalars().all())


async def build_heatmap(
    db: AsyncSession,
    width_cells: int,
    height_cells: int,
    step_cm: int,
) -> dict:
    rows = await get_measurements(db, limit=500)
    if len(rows) < 3:
        return {'error': 'Not enough data to build heatmap', 'points': []}

    data = [{'x': item.x, 'y': item.y, 'rssi': item.rssi} for item in rows]
    return {
        'heatmap': interpolate_heatmap(data, width_cells, height_cells, step_cm),
        'measurements': data,
        'width_cells': width_cells,
        'height_cells': height_cells,
        'step_cm': step_cm,
        'total_points': len(data),
    }


async def clear_measurements(db: AsyncSession) -> None:
    await db.execute(delete(WiFiMeasurement))
    await db.commit()


async def save_heatmap_snapshot(db: AsyncSession, name: str) -> SavedHeatmap:
    measurements = await get_measurements(db, limit=500)
    data = [
        {'x': item.x, 'y': item.y, 'rssi': item.rssi, 'step_cm': item.step_cm}
        for item in measurements
    ]
    saved = SavedHeatmap(name=name, data=data)
    db.add(saved)
    await db.commit()
    await db.refresh(saved)
    return saved


async def get_saved_heatmaps(db: AsyncSession) -> list[SavedHeatmap]:
    result = await db.execute(select(SavedHeatmap).order_by(SavedHeatmap.created_at.desc()))
    return list(result.scalars().all())


async def get_saved_heatmap(db: AsyncSession, heatmap_id: int) -> SavedHeatmap | None:
    result = await db.execute(select(SavedHeatmap).where(SavedHeatmap.id == heatmap_id))
    return result.scalar_one_or_none()
