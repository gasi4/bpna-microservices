import cv2
import numpy as np
from ultralytics import YOLO

from app.core.config import YOLO_MODEL_PATH
from app.services.distance import estimate_distance_cm


model: YOLO | None = None


def get_model() -> YOLO:
    global model
    if model is None:
        model = YOLO(YOLO_MODEL_PATH)
    return model


def detect_objects(jpeg_bytes: bytes) -> dict:
    model_instance = get_model()
    arr = np.frombuffer(jpeg_bytes, dtype=np.uint8)
    image = cv2.imdecode(arr, cv2.IMREAD_COLOR)

    if image is None:
        return {"boxes": [], "frame_width": 0, "frame_height": 0}

    h, w = image.shape[:2]
    lab = cv2.cvtColor(image, cv2.COLOR_BGR2LAB)
    l, a, b = cv2.split(lab)
    clahe = cv2.createCLAHE(clipLimit=2.5, tileGridSize=(8, 8))
    enhanced = cv2.merge([clahe.apply(l), a, b])
    enhanced = cv2.cvtColor(enhanced, cv2.COLOR_LAB2BGR)

    results = model_instance(enhanced, verbose=False, conf=0.20, iou=0.40)
    boxes: list[dict] = []

    for box in results[0].boxes:
        x1, y1, x2, y2 = [int(v) for v in box.xyxy[0].tolist()]
        cls_id = int(box.cls[0])
        conf = float(box.conf[0])
        label = model_instance.names[cls_id]

        margin_x = int((x2 - x1) * 0.15)
        margin_y = int((y2 - y1) * 0.15)
        x1 = max(0, x1 - margin_x)
        y1 = max(0, y1 - margin_y)
        x2 = min(w, x2 + margin_x)
        y2 = min(h, y2 + margin_y)

        boxes.append(
            {
                "x1": x1,
                "y1": y1,
                "x2": x2,
                "y2": y2,
                "label": label,
                "conf": round(conf, 2),
                "track_id": None,
                "distance_cm": estimate_distance_cm(label, max(1.0, float(x2 - x1))),
            }
        )

    return {"boxes": boxes, "frame_width": w, "frame_height": h}
