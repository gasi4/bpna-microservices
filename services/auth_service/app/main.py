import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.core.database import Base, SessionLocal, engine
from app.models import device as device_model  # noqa: F401
from app.models import onboarding as onboarding_model  # noqa: F401
from app.models import user as user_model  # noqa: F401
from app.routers.admin import router as admin_router
from app.routers.auth import router as auth_router
from app.routers.health import router as health_router
from app.services.auth_service import create_default_users


logger = logging.getLogger(__name__)


async def run_startup_setup() -> None:
    last_error: Exception | None = None

    for attempt in range(1, 16):
        try:
            async with engine.begin() as conn:
                await conn.run_sync(Base.metadata.create_all)
                await conn.exec_driver_sql(
                    "ALTER TABLE users ADD COLUMN IF NOT EXISTS role VARCHAR(20) DEFAULT 'operator'"
                )
                await conn.exec_driver_sql(
                    "ALTER TABLE users ADD COLUMN IF NOT EXISTS created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP"
                )
                await conn.exec_driver_sql(
                    "UPDATE users SET created_at = CURRENT_TIMESTAMP WHERE created_at IS NULL"
                )
                await conn.exec_driver_sql(
                    "ALTER TABLE devices ADD COLUMN IF NOT EXISTS created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP"
                )
                await conn.exec_driver_sql(
                    "ALTER TABLE devices ADD COLUMN IF NOT EXISTS chip_id VARCHAR(64)"
                )
                await conn.exec_driver_sql(
                    "CREATE UNIQUE INDEX IF NOT EXISTS ix_devices_chip_id_unique "
                    "ON devices (chip_id) WHERE chip_id IS NOT NULL"
                )
                await conn.exec_driver_sql(
                    "UPDATE devices SET created_at = CURRENT_TIMESTAMP WHERE created_at IS NULL"
                )
            async with SessionLocal() as db:
                await create_default_users(db)
            return
        except Exception as exc:  # noqa: BLE001
            last_error = exc
            logger.warning("Auth startup attempt %s failed: %s", attempt, exc)
            await asyncio.sleep(2)

    if last_error is not None:
        raise last_error


@asynccontextmanager
async def lifespan(app: FastAPI):
    await run_startup_setup()
    yield
    await engine.dispose()


app = FastAPI(title="BPNA Auth Service", version="1.0.0", lifespan=lifespan)
app.include_router(auth_router)
app.include_router(admin_router)
app.include_router(health_router)
