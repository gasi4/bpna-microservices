import httpx

from app.core.config import settings


async def save_telemetry(data: dict) -> None:
    try:
        payload = {key: value for key, value in data.items() if key != "type"}
        async with httpx.AsyncClient(timeout=5) as client:
            await client.post(
                f"{settings.telemetry_service_url}/internal/telemetry",
                json=payload,
            )
    except Exception as exc:
        print(f"[device] telemetry save failed: {exc}")
