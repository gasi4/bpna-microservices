import httpx

from app.core.config import settings


async def validate_token(token: str) -> bool:
    async with httpx.AsyncClient(timeout=5) as client:
        response = await client.get(
            f"{settings.auth_service_url}/validate",
            headers={"Authorization": f"Bearer {token}"},
        )
    return response.status_code == 200


async def validate_device_credentials(device_id: str, secret: str) -> dict | None:
    try:
        async with httpx.AsyncClient(timeout=5) as client:
            response = await client.post(
                f"{settings.auth_service_url}/devices/validate",
                json={"device_id": device_id, "secret": secret},
            )
    except Exception:
        return None

    if response.status_code != 200:
        return None
    return response.json()
