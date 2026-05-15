import json
from datetime import datetime, timezone

from fastapi import APIRouter, Query, WebSocket, WebSocketDisconnect

from app.core.auth_client import validate_token
from app.core.config import settings
from app.schemas.command import CommandRequest
from app.services import state
from app.services.broadcast import broadcast_text
from app.services.command_service import send_command_to_device
from app.services.frame_service import handle_frame
from app.services.message_service import handle_text_message


router = APIRouter()


@router.websocket("/ws/esp")
async def esp_ws(websocket: WebSocket, secret: str = Query(...)):
    if secret != settings.device_secret:
        await websocket.close(code=1008)
        return

    await websocket.accept()
    state.device_ws = websocket
    state.device_state["connected"] = True
    state.device_state["last_seen"] = datetime.now(timezone.utc).isoformat()

    try:
        while True:
            message = await websocket.receive()

            if message["type"] == "websocket.receive" and message.get("bytes"):
                await handle_frame(message["bytes"])
            elif message["type"] == "websocket.receive" and message.get("text"):
                await handle_text_message(websocket, message["text"])

    except WebSocketDisconnect:
        pass
    finally:
        if state.device_ws is websocket:
            state.device_ws = None
        state.device_state["connected"] = False
        state.device_state["last_data"] = None
        await broadcast_text(state.telemetry_viewers, json.dumps({"connected": False}))


@router.websocket("/ws/view")
async def video_view(websocket: WebSocket, token: str = Query(...)):
    if not await validate_token(token):
        await websocket.close(code=1008)
        return

    await websocket.accept()
    state.video_viewers.add(websocket)
    try:
        while True:
            await websocket.receive_text()
    except Exception:
        pass
    finally:
        state.video_viewers.discard(websocket)


@router.websocket("/ws/telemetry")
async def telemetry_view(websocket: WebSocket, token: str = Query(...)):
    if not await validate_token(token):
        await websocket.close(code=1008)
        return

    await websocket.accept()
    state.telemetry_viewers.add(websocket)
    await websocket.send_text(json.dumps(state.device_state))
    try:
        while True:
            await websocket.receive_text()
    except Exception:
        pass
    finally:
        state.telemetry_viewers.discard(websocket)


@router.post("/internal/command")
async def internal_command(data: CommandRequest):
    success = await send_command_to_device(data.command)
    return {"success": success, "command": data.command}


@router.get("/state")
async def get_state():
    return state.device_state
