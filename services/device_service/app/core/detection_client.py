import httpx

from app.core.config import settings


async def detect_frame(frame: bytes) -> dict:
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            response = await client.post(
                f"{settings.detection_service_url}/detect",
                files={"frame": ("frame.jpg", frame, "image/jpeg")},
            )
        if response.status_code == 200:
            return response.json()
    except Exception as exc:
        print(f"[device] detection unavailable: {exc}")

    return {"boxes": [], "frame_width": 0, "frame_height": 0}
