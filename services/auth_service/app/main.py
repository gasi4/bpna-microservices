from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.core.database import Base, SessionLocal, engine
from app.models import device as device_model  # noqa: F401
from app.models import user as user_model  # noqa: F401
from app.routers.admin import router as admin_router
from app.routers.auth import router as auth_router
from app.routers.health import router as health_router
from app.services.auth_service import create_default_users


@asynccontextmanager
async def lifespan(app: FastAPI):
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        await conn.exec_driver_sql("ALTER TABLE users ADD COLUMN IF NOT EXISTS role VARCHAR(20) DEFAULT 'operator'")
    async with SessionLocal() as db:
        await create_default_users(db)
    yield
    await engine.dispose()


app = FastAPI(title="BPNA Auth Service", version="1.0.0", lifespan=lifespan)
app.include_router(auth_router)
app.include_router(admin_router)
app.include_router(health_router)
