import httpx

from app.core.config import settings


async def notify_scan_step(command: str, device_id: str) -> None:
    try:
        async with httpx.AsyncClient(timeout=5) as client:
            await client.post(
                f"{settings.wifi_service_url}/internal/step",
                json={"command": command, "device_id": device_id},
            )
    except Exception:
        pass
