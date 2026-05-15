import json

from fastapi import WebSocket

from app.services.state import get_device_state


async def broadcast_measurement(device_id: str, payload: dict) -> None:
    dead = set()
    message = json.dumps(payload)
    state = get_device_state(device_id)
    for client in set(state.wifi_viewers):
        try:
            await client.send_text(message)
        except Exception:
            dead.add(client)
    state.wifi_viewers.difference_update(dead)


async def broadcast_event(device_id: str, payload: dict) -> None:
    dead = set()
    message = json.dumps(payload)
    state = get_device_state(device_id)
    for client in set(state.wifi_viewers):
        try:
            await client.send_text(message)
        except Exception:
            dead.add(client)
    state.wifi_viewers.difference_update(dead)


async def register_wifi_viewer(websocket: WebSocket, device_id: str) -> None:
    await websocket.accept()
    state = get_device_state(device_id)
    state.wifi_viewers.add(websocket)
    try:
        while True:
            await websocket.receive_text()
    except Exception:
        pass
    finally:
        state.wifi_viewers.discard(websocket)
