import httpx

from app.core.config import settings


async def save_wifi_measurement(data: dict) -> None:
    try:
        async with httpx.AsyncClient(timeout=5) as client:
            await client.post(
                f"{settings.wifi_service_url}/internal/measurements",
                json=data,
            )
    except Exception as exc:
        print(f"[device] wifi measurement save failed: {exc}")
