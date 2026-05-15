from collections import defaultdict

from fastapi import WebSocket


device_ws_by_id: dict[str, WebSocket] = {}
video_viewers_by_device: dict[str, set[WebSocket]] = defaultdict(set)
telemetry_viewers_by_device: dict[str, set[WebSocket]] = defaultdict(set)
last_frame_by_device: dict[str, bytes] = {}
device_states: dict[str, dict] = {}


def ensure_device_state(device_id: str, *, name: str | None = None) -> dict:
    state = device_states.setdefault(
        device_id,
        {
            "device_id": device_id,
            "name": name or device_id,
            "connected": False,
            "last_seen": None,
            "last_data": None,
            "last_detection": {"boxes": [], "frame_width": 0, "frame_height": 0},
        },
    )
    if name:
        state["name"] = name
    return state


def get_device_state(device_id: str) -> dict:
    return ensure_device_state(device_id)


def get_all_device_states() -> list[dict]:
    return [ensure_device_state(device_id) for device_id in sorted(device_states)]
