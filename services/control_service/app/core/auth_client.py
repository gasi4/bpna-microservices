import httpx
from fastapi import Header, HTTPException, status

from app.core.config import settings


async def require_user(authorization: str | None = Header(default=None)) -> dict:
    if not authorization:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED)

    async with httpx.AsyncClient(timeout=5) as client:
        response = await client.get(
            f"{settings.auth_service_url}/validate",
            headers={"Authorization": authorization},
        )

    if response.status_code != 200:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED)
    return response.json()
