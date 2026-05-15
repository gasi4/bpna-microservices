import httpx
from fastapi import APIRouter

from app.core.routes import SERVICE_ROUTES


router = APIRouter()


@router.get("/health")
async def health():
    checks = {}
    async with httpx.AsyncClient(timeout=5) as client:
        for name, url in SERVICE_ROUTES.items():
            try:
                response = await client.get(f"{url}/health")
                checks[name] = response.status_code == 200
            except Exception:
                checks[name] = False
    return {"status": "ok" if all(checks.values()) else "degraded", "services": checks}
