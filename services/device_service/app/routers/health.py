from fastapi import APIRouter

from app.services import state


router = APIRouter()


@router.get("/health")
async def health():
    connected = sum(1 for item in state.device_states.values() if item.get("connected"))
    return {"status": "ok", "service": "device", "connected_devices": connected}
