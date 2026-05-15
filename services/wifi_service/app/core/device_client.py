import httpx

from app.core.config import settings


async def send_device_command(command: str) -> None:
    async with httpx.AsyncClient(timeout=5) as client:
        await client.post(
            f"{settings.device_service_url}/internal/command",
            json={"command": command},
        )
