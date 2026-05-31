import json
from typing import Any

from app.services import state


async def send_command_to_device(device_id: str, payload: dict[str, Any]) -> bool:
    websocket = state.device_ws_by_id.get(device_id)
    if websocket is None:
        return False

    try:
        await websocket.send_text(json.dumps(payload))
        return True
    except Exception:
        if state.device_ws_by_id.get(device_id) is websocket:
            state.device_ws_by_id.pop(device_id, None)
        device_state = state.ensure_device_state(device_id)
        device_state["connected"] = False
        return False
