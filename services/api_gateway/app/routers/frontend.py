from pathlib import Path

from fastapi import APIRouter
from fastapi.responses import FileResponse

from app.core.config import settings


router = APIRouter()


@router.get("/")
async def root():
    return FileResponse(Path(settings.static_dir) / "index.html")
