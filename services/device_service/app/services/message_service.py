import json
from datetime import datetime, timezone

from fastapi import WebSocket

from app.core.telemetry_client import save_telemetry
from app.core.wifi_client import save_wifi_measurement
from app.services import state
from app.services.broadcast import broadcast_text


async def handle_text_message(websocket: WebSocket, device_id: str, raw: str) -> None:
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return

    msg_type = data.get("type")
    device_state = state.ensure_device_state(device_id)

    if msg_type == "telemetry":
        data["device_id"] = device_id
        device_state["last_seen"] = datetime.now(timezone.utc).isoformat()
        device_state["last_data"] = data
        await save_telemetry(data)
        await broadcast_text(
            state.telemetry_viewers_by_device[device_id],
            json.dumps(
                {
                    "connected": True,
                    **{key: value for key, value in data.items() if key != "type"},
                }
            ),
        )
    elif msg_type == "wifi_measurement":
        data["device_id"] = device_id
        await save_wifi_measurement(data)
    elif msg_type == "ping":
        await websocket.send_text(json.dumps({"type": "pong"}))
