from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.core.database import Base, SessionLocal, engine
from app.routers.auth import router as auth_router
from app.routers.health import router as health_router
from app.services.auth_service import create_default_operator


@asynccontextmanager
async def lifespan(app: FastAPI):
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    async with SessionLocal() as db:
        await create_default_operator(db)
    yield
    await engine.dispose()


app = FastAPI(title="BPNA Auth Service", version="1.0.0", lifespan=lifespan)
app.include_router(auth_router)
app.include_router(health_router)
