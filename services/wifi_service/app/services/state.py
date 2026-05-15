from fastapi import WebSocket


wifi_viewers: set[WebSocket] = set()
drone_track: list[dict] = []
scan_running = False
