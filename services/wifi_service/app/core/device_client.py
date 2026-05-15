import httpx

from app.core.config import settings


async def send_device_command(command: str) -> bool:
    try:
        async with httpx.AsyncClient(timeout=5) as client:
            response = await client.post(
                f"{settings.device_service_url}/internal/command",
                json={"command": command},
            )
        return response.status_code == 200 and bool(response.json().get("success"))
    except Exception:
        return False


async def get_device_state() -> dict:
    try:
        async with httpx.AsyncClient(timeout=5) as client:
            response = await client.get(f"{settings.device_service_url}/state")
        if response.status_code == 200:
            return response.json()
    except Exception:
        pass
    return {"connected": False, "last_data": None, "last_detection": {"boxes": []}}
