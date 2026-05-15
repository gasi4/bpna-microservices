import httpx

from app.core.config import settings


async def notify_scan_step(command: str) -> None:
    try:
        async with httpx.AsyncClient(timeout=5) as client:
            await client.post(
                f"{settings.wifi_service_url}/internal/step",
                json={"command": command},
            )
    except Exception:
        pass
