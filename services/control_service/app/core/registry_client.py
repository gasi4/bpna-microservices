import httpx

from app.core.config import settings


async def get_registered_devices(authorization: str) -> list[dict]:
    async with httpx.AsyncClient(timeout=5) as client:
        response = await client.get(
            f"{settings.auth_service_url}/devices",
            headers={"Authorization": authorization},
        )
    if response.status_code != 200:
        return []
    return list(response.json())
