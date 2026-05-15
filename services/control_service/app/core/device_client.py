import httpx

from app.core.config import settings


async def dispatch_command(command: str) -> bool:
    async with httpx.AsyncClient(timeout=5) as client:
        response = await client.post(
            f"{settings.device_service_url}/internal/command",
            json={"command": command},
        )
    if response.status_code != 200:
        return False
    return bool(response.json().get("success"))
