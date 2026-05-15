from fastapi import FastAPI

from app.routers.detection import router as detection_router
from app.routers.health import router as health_router


app = FastAPI(title="BPNA Detection Service", version="1.0.0")
app.include_router(detection_router)
app.include_router(health_router)
