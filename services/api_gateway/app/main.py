from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from app.core.config import settings
from app.routers.frontend import router as frontend_router
from app.routers.health import router as health_router
from app.routers.proxy import router as proxy_router


app = FastAPI(title="BPNA API Gateway", version="1.0.0")
app.mount("/static", StaticFiles(directory=settings.static_dir), name="static")
app.include_router(frontend_router)
app.include_router(proxy_router)
app.include_router(health_router)
