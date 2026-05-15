from fastapi import APIRouter

from app.core.config import YOLO_MODEL_PATH


router = APIRouter()


@router.get("/health")
async def health():
    return {"status": "ok", "service": "detection", "model": YOLO_MODEL_PATH}
