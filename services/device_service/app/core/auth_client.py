import httpx

from app.core.config import settings


async def validate_token(token: str) -> bool:
    async with httpx.AsyncClient(timeout=5) as client:
        response = await client.get(
            f"{settings.auth_service_url}/validate",
            headers={"Authorization": f"Bearer {token}"},
        )
    return response.status_code == 200
