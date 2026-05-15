import json

from app.core.detection_client import detect_frame
from app.services import state
from app.services.broadcast import broadcast_bytes, broadcast_text


async def handle_frame(device_id: str, frame: bytes) -> None:
    device_state = state.ensure_device_state(device_id)
    state.last_frame_by_device[device_id] = frame
    await broadcast_bytes(state.video_viewers_by_device[device_id], frame)
    detection = await detect_frame(frame)
    device_state["last_detection"] = detection
    await broadcast_text(
        state.video_viewers_by_device[device_id],
        json.dumps({"type": "detections", "device_id": device_id, **detection}),
    )
