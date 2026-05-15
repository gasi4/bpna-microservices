from sqlalchemy.ext.asyncio import AsyncSession

from app.core.device_client import send_device_command
from app.services import state
from app.services.wifi_service import clear_measurements


async def start_scan(
    db: AsyncSession,
    width: int,
    height: int,
    step_cm: int,
) -> dict:
    state.scan_running = True
    await clear_measurements(db)
    state.drone_track.clear()
    await send_device_command("stop")
    return {
        "status": "scan_started",
        "width": width,
        "height": height,
        "step_cm": step_cm,
    }


async def stop_scan() -> dict:
    state.scan_running = False
    await send_device_command("stop")
    return {"status": "scan_stopped"}
