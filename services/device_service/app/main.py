from fastapi import FastAPI

from app.routers.device import router as device_router
from app.routers.health import router as health_router


app = FastAPI(title="BPNA Device Service", version="1.0.0")
app.include_router(device_router)
app.include_router(health_router)
