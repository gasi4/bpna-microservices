from fastapi import FastAPI

from app.routers.control import router as control_router
from app.routers.health import router as health_router


app = FastAPI(title="BPNA Control Service", version="1.0.0")
app.include_router(control_router)
app.include_router(health_router)
