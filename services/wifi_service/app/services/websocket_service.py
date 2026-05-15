import json

from fastapi import WebSocket

from app.services.state import wifi_viewers


async def broadcast_measurement(payload: dict) -> None:
    dead = set()
    message = json.dumps(payload)
    for client in set(wifi_viewers):
        try:
            await client.send_text(message)
        except Exception:
            dead.add(client)
    wifi_viewers.difference_update(dead)


async def register_wifi_viewer(websocket: WebSocket) -> None:
    await websocket.accept()
    wifi_viewers.add(websocket)
    try:
        while True:
            await websocket.receive_text()
    except Exception:
        pass
    finally:
        wifi_viewers.discard(websocket)
