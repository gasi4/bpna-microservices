from fastapi import APIRouter, Depends, Header, HTTPException

from app.core.auth_client import require_user
from app.schemas.command import CommandCreate, CommandResponse
from app.services.autopilot_state import get_autopilot_state
from app.services.control_service import (
    claim_device_control,
    heartbeat_device_control,
    list_devices_with_status,
    release_device_control,
    send_manual_command,
    toggle_autopilot,
)


router = APIRouter()


@router.get("/devices")
async def devices(authorization: str | None = Header(default=None), user: dict = Depends(require_user)):
    if not authorization:
        raise HTTPException(status_code=401, detail="Authorization header is required")
    items = await list_devices_with_status(authorization)
    for item in items:
        item["you_control"] = item.get("controller_user_id") == user.get("user_id")
    return items


@router.post("/devices/{device_id}/claim")
async def claim(device_id: str, user: dict = Depends(require_user)):
    return await claim_device_control(device_id, user)


@router.post("/devices/{device_id}/release")
async def release(device_id: str, user: dict = Depends(require_user)):
    return await release_device_control(device_id, user)


@router.post("/devices/{device_id}/heartbeat")
async def heartbeat(device_id: str, user: dict = Depends(require_user)):
    return await heartbeat_device_control(device_id, user)


@router.post("/command", response_model=CommandResponse)
async def command(data: CommandCreate, user: dict = Depends(require_user)):
    return await send_manual_command(data, user)


@router.post("/autopilot")
async def autopilot(
    enabled: bool,
    device_id: str = "bpna-01",
    target_id: int | None = None,
    target_label: str | None = None,
    user: dict = Depends(require_user),
):
    return await toggle_autopilot(device_id, enabled, target_id, target_label, user)


@router.get("/autopilot/status")
async def autopilot_status(device_id: str = "bpna-01", user: dict = Depends(require_user)):
    return get_autopilot_state(device_id)


@router.get("/status")
async def status_endpoint(device_id: str = "bpna-01", user: dict = Depends(require_user)):
    return {"device": device_id, "operator": user.get("username")}
