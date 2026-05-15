from pydantic import BaseModel


class DetectionBox(BaseModel):
    x1: int
    y1: int
    x2: int
    y2: int
    label: str
    conf: float
    track_id: int | None = None
    distance_cm: float | None = None


class DetectionResponse(BaseModel):
    boxes: list[DetectionBox]
    frame_width: int
    frame_height: int
