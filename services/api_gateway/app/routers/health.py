import asyncio
import httpx
from fastapi import APIRouter

from app.core.routes import SERVICE_ROUTES


router = APIRouter()


@router.get("/health")
async def health():
    async def check_service(client: httpx.AsyncClient, name: str, url: str) -> tuple[str, bool]:
        try:
            response = await client.get(f"{url}/health")
            return name, response.status_code == 200
        except Exception:
            return name, False

    async with httpx.AsyncClient(timeout=2) as client:
        results = await asyncio.gather(
            *(check_service(client, name, url) for name, url in SERVICE_ROUTES.items())
        )
    checks = dict(results)
    return {"status": "ok" if all(checks.values()) else "degraded", "services": checks}
