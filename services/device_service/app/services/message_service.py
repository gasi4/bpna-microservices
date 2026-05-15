import json
from datetime import datetime, timezone

from fastapi import WebSocket

from app.core.telemetry_client import save_telemetry
from app.core.wifi_client import save_wifi_measurement
from app.services import state
from app.services.broadcast import broadcast_text


async def handle_text_message(websocket: WebSocket, raw: str) -> None:
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return

    msg_type = data.get("type")

    if msg_type == "telemetry":
        state.device_state["last_seen"] = datetime.now(timezone.utc).isoformat()
        state.device_state["last_data"] = data
        await save_telemetry(data)
        await broadcast_text(
            state.telemetry_viewers,
            json.dumps(
                {
                    "connected": True,
                    **{key: value for key, value in data.items() if key != "type"},
                }
            ),
        )
    elif msg_type == "wifi_measurement":
        await save_wifi_measurement(data)
    elif msg_type == "ping":
        await websocket.send_text(json.dumps({"type": "pong"}))
