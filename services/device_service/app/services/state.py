from fastapi import WebSocket


device_ws: WebSocket | None = None
video_viewers: set[WebSocket] = set()
telemetry_viewers: set[WebSocket] = set()

device_state: dict = {
    "connected": False,
    "last_seen": None,
    "last_data": None,
}
