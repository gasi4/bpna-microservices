from fastapi import APIRouter, Depends

from app.core.auth_client import require_user
from app.schemas.command import CommandCreate, CommandResponse
from app.services.autopilot_state import autopilot_state
from app.services.control_service import send_manual_command, toggle_autopilot


router = APIRouter()


@router.post("/command", response_model=CommandResponse)
async def command(data: CommandCreate, user: dict = Depends(require_user)):
    return await send_manual_command(data)


@router.post("/autopilot")
async def autopilot(
    enabled: bool,
    target_id: int | None = None,
    target_label: str | None = None,
    user: dict = Depends(require_user),
):
    return await toggle_autopilot(enabled, target_id, target_label)


@router.get("/autopilot/status")
async def autopilot_status(user: dict = Depends(require_user)):
    return autopilot_state


@router.get("/status")
async def status_endpoint(user: dict = Depends(require_user)):
    return {"device": "bpna-01", "operator": user.get("username")}
