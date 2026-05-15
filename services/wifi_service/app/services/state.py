import asyncio
from typing import Literal

from fastapi import WebSocket


wifi_viewers: set[WebSocket] = set()
drone_track: list[dict] = []
scan_running = False
scan_task: asyncio.Task | None = None
scan_mode: Literal["manual", "autopilot"] = "manual"
scan_session_id: str | None = None
scan_width = 10
scan_height = 10
scan_step_cm = 100
current_x = 0
current_y = 0
heading: Literal["east", "south", "west", "north"] = "east"
row_direction = 1
