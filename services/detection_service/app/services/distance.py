FOCAL_LENGTH_PX = 700.0

KNOWN_WIDTHS_CM: dict[str, float] = {
    "person": 45.0,
    "bicycle": 60.0,
    "motorcycle": 80.0,
    "car": 180.0,
    "dog": 35.0,
    "cat": 18.0,
    "chair": 45.0,
    "bottle": 7.0,
    "box": 30.0,
    "backpack": 40.0,
}


def estimate_distance_cm(label: str, pixel_width: float) -> float | None:
    if pixel_width <= 0:
        return None
    real_width_cm = KNOWN_WIDTHS_CM.get(label, 40.0)
    return round((real_width_cm * FOCAL_LENGTH_PX) / pixel_width, 1)
