import asyncio
from dataclasses import dataclass, field
from typing import Literal

from fastapi import WebSocket


Heading = Literal["east", "south", "west", "north"]
ScanMode = Literal["manual", "autopilot"]


@dataclass
class DeviceScanState:
    wifi_viewers: set[WebSocket] = field(default_factory=set)
    drone_track: list[dict] = field(default_factory=list)
    scan_running: bool = False
    scan_task: asyncio.Task | None = None
    scan_mode: ScanMode = "manual"
    scan_session_id: str | None = None
    scan_width: int = 10
    scan_height: int = 10
    scan_step_cm: int = 100
    current_x: int = 0
    current_y: int = 0
    heading: Heading = "east"
    row_direction: int = 1


_device_states: dict[str, DeviceScanState] = {}


def get_device_state(device_id: str) -> DeviceScanState:
    state = _device_states.get(device_id)
    if state is None:
        state = DeviceScanState()
        _device_states[device_id] = state
    return state
