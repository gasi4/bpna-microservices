import httpx

from app.core.config import settings


async def dispatch_command(command: str, device_id: str) -> bool:
    async with httpx.AsyncClient(timeout=5) as client:
        response = await client.post(
            f"{settings.device_service_url}/internal/command",
            json={"device_id": device_id, "command": command},
        )
    if response.status_code != 200:
        return False
    return bool(response.json().get("success"))


async def get_device_states() -> list[dict]:
    async with httpx.AsyncClient(timeout=5) as client:
        response = await client.get(f"{settings.device_service_url}/states")
    if response.status_code != 200:
        return []
    return list(response.json().get("devices") or [])
