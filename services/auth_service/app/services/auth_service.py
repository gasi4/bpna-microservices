import secrets
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import hash_password, verify_password
from app.models.device import Device
from app.models.user import User


async def authenticate_user(
    db: AsyncSession,
    username: str,
    password: str,
) -> User | None:
    result = await db.execute(select(User).where(User.username == username))
    user = result.scalar_one_or_none()
    if not user or not user.is_active or not verify_password(password, user.password):
        return None
    return user


async def create_default_users(db: AsyncSession) -> None:
    defaults = [
        ("admin", "admin123", "admin"),
        ("operator", "operator123", "operator"),
    ]
    for username, password, role in defaults:
        result = await db.execute(select(User).where(User.username == username))
        if result.scalar_one_or_none() is None:
            db.add(User(username=username, password=hash_password(password), role=role))

    result = await db.execute(select(Device).where(Device.device_id == "bpna-01"))
    if result.scalar_one_or_none() is None:
        db.add(Device(name="Platform 1", device_id="bpna-01", device_secret="change-me-device"))

    await db.commit()


async def list_users(db: AsyncSession) -> list[User]:
    result = await db.execute(select(User).order_by(User.username))
    return list(result.scalars().all())


async def create_user(db: AsyncSession, username: str, password: str, role: str) -> User:
    role = role if role in {"admin", "operator"} else "operator"
    user = User(username=username, password=hash_password(password), role=role)
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user


async def deactivate_user(db: AsyncSession, user_id: int) -> bool:
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if user is None:
        return False
    user.is_active = False
    await db.commit()
    return True


async def list_devices(db: AsyncSession) -> list[Device]:
    result = await db.execute(
        select(Device).where(Device.is_active == True).order_by(Device.name, Device.device_id)
    )
    return list(result.scalars().all())


async def _next_device_id(db: AsyncSession) -> str:
    result = await db.execute(select(Device.device_id))
    existing = {value for value in result.scalars().all() if value}
    index = 1
    while True:
        candidate = f"bpna-{index:03d}"
        if candidate not in existing:
            return candidate
        index += 1


async def create_device(db: AsyncSession, name: str, device_id: str | None = None) -> Device:
    normalized_device_id = (device_id or "").strip() or await _next_device_id(db)
    secret = secrets.token_urlsafe(24)
    device = Device(name=name.strip() or normalized_device_id, device_id=normalized_device_id, device_secret=secret)
    db.add(device)
    await db.commit()
    await db.refresh(device)
    return device


async def deactivate_device(db: AsyncSession, device_id: str) -> bool:
    result = await db.execute(select(Device).where(Device.device_id == device_id))
    device = result.scalar_one_or_none()
    if device is None:
        return False
    device.is_active = False
    await db.commit()
    return True


async def validate_device_credentials(db: AsyncSession, device_id: str, secret: str) -> Device | None:
    result = await db.execute(select(Device).where(Device.device_id == device_id))
    device = result.scalar_one_or_none()
    if device is None or not device.is_active or device.device_secret != secret:
        return None
    return device
