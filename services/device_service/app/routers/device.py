import json
from datetime import datetime, timezone

from fastapi import APIRouter, Query, WebSocket, WebSocketDisconnect

from app.core.auth_client import validate_device_credentials, validate_token
from app.schemas.command import CommandRequest
from app.services import state
from app.services.broadcast import broadcast_text
from app.services.command_service import send_command_to_device
from app.services.frame_service import handle_frame
from app.services.message_service import handle_text_message


router = APIRouter()


@router.websocket("/ws/esp")
async def esp_ws(websocket: WebSocket, device_id: str = Query("bpna-01"), secret: str = Query(...)):
    device = await validate_device_credentials(device_id, secret)
    if device is None:
        await websocket.close(code=1008)
        return

    await websocket.accept()
    state.device_ws_by_id[device_id] = websocket
    device_state = state.ensure_device_state(device_id, name=device.get("name"))
    device_state["connected"] = True
    device_state["last_seen"] = datetime.now(timezone.utc).isoformat()

    try:
        while True:
            message = await websocket.receive()

            if message["type"] == "websocket.receive" and message.get("bytes"):
                await handle_frame(device_id, message["bytes"])
            elif message["type"] == "websocket.receive" and message.get("text"):
                await handle_text_message(websocket, device_id, message["text"])

    except WebSocketDisconnect:
        pass
    finally:
        if state.device_ws_by_id.get(device_id) is websocket:
            state.device_ws_by_id.pop(device_id, None)
        device_state = state.ensure_device_state(device_id)
        device_state["connected"] = False
        await broadcast_text(
            state.telemetry_viewers_by_device[device_id],
            json.dumps({"connected": False, "device_id": device_id}),
        )


@router.websocket("/ws/view")
async def video_view(websocket: WebSocket, token: str = Query(...), device_id: str = Query("bpna-01")):
    if not await validate_token(token):
        await websocket.close(code=1008)
        return

    await websocket.accept()
    viewers = state.video_viewers_by_device[device_id]
    viewers.add(websocket)

    last_frame = state.last_frame_by_device.get(device_id)
    if last_frame:
        await websocket.send_bytes(last_frame)
        detection = state.ensure_device_state(device_id).get("last_detection") or {"boxes": []}
        await websocket.send_text(json.dumps({"type": "detections", "device_id": device_id, **detection}))
    try:
        while True:
            await websocket.receive_text()
    except Exception:
        pass
    finally:
        viewers.discard(websocket)


@router.websocket("/ws/telemetry")
async def telemetry_view(websocket: WebSocket, token: str = Query(...), device_id: str = Query("bpna-01")):
    if not await validate_token(token):
        await websocket.close(code=1008)
        return

    await websocket.accept()
    viewers = state.telemetry_viewers_by_device[device_id]
    viewers.add(websocket)
    await websocket.send_text(json.dumps(state.ensure_device_state(device_id)))
    try:
        while True:
            await websocket.receive_text()
    except Exception:
        pass
    finally:
        viewers.discard(websocket)


@router.post("/internal/command")
async def internal_command(data: CommandRequest):
    success = await send_command_to_device(data.device_id, data.command)
    return {"success": success, "command": data.command, "device_id": data.device_id}


@router.get("/state/{device_id}")
async def get_state(device_id: str):
    return state.ensure_device_state(device_id)


@router.get("/states")
async def get_states():
    return {"devices": state.get_all_device_states()}
