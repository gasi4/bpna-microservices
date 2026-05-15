import json

from app.core.detection_client import detect_frame
from app.services import state
from app.services.broadcast import broadcast_bytes, broadcast_text


async def handle_frame(frame: bytes) -> None:
    await broadcast_bytes(state.video_viewers, frame)
    detection = await detect_frame(frame)
    state.device_state["last_detection"] = detection
    await broadcast_text(
        state.video_viewers,
        json.dumps({"type": "detections", **detection}),
    )
