from fastapi import APIRouter

from app.services.state import device_state


router = APIRouter()


@router.get("/health")
async def health():
    return {"status": "ok", "service": "device", "connected": device_state["connected"]}
