from fastapi import APIRouter, File, UploadFile

from app.schemas.detection import DetectionResponse
from app.services.detection_service import detect_objects


router = APIRouter()


@router.post("/detect", response_model=DetectionResponse)
async def detect(frame: UploadFile = File(...)):
    return detect_objects(await frame.read())
