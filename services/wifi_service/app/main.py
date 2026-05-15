from contextlib import asynccontextmanager

from fastapi import FastAPI
from sqlalchemy import text

from app.core.database import Base, engine
from app.routers.health import router as health_router
from app.routers.wifi import router as wifi_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        await conn.execute(text("ALTER TABLE wifi_measurements ADD COLUMN IF NOT EXISTS device_id VARCHAR(64) DEFAULT 'bpna-01'"))
        await conn.execute(text("ALTER TABLE saved_heatmaps ADD COLUMN IF NOT EXISTS device_id VARCHAR(64) DEFAULT 'bpna-01'"))
    yield
    await engine.dispose()


app = FastAPI(title="BPNA Wi-Fi Service", version="1.0.0", lifespan=lifespan)
app.include_router(wifi_router)
app.include_router(health_router)
