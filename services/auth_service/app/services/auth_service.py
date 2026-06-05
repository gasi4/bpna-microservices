import secrets
from datetime import datetime, timezone

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import hash_password, verify_password
from app.models.device import Device
from app.models.onboarding import DeviceOnboardingRequest, DevicePairingToken
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


async def delete_user(db: AsyncSession, user_id: int) -> bool:
    result = await db.execute(delete(User).where(User.id == user_id))
    await db.commit()
    return bool(result.rowcount)


async def list_devices(db: AsyncSession, include_inactive: bool = False) -> list[Device]:
    query = select(Device).order_by(Device.name, Device.device_id)
    if not include_inactive:
        query = query.where(Device.is_active == True)
    result = await db.execute(query)
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


def _normalize_chip_id(chip_id: str) -> str:
    return chip_id.strip().upper()


def _normalize_module_name(module_name: str, chip_id: str) -> str:
    return module_name.strip()[:120] or f"BPNA-{chip_id[-8:]}"


def _new_pairing_token() -> str:
    return f"bpna-pair-{secrets.token_urlsafe(18)}"


async def create_device(
    db: AsyncSession,
    name: str,
    device_id: str | None = None,
    chip_id: str | None = None,
) -> Device:
    normalized_device_id = (device_id or "").strip() or await _next_device_id(db)
    secret = secrets.token_urlsafe(24)
    device = Device(
        name=name.strip() or normalized_device_id,
        device_id=normalized_device_id,
        chip_id=_normalize_chip_id(chip_id) if chip_id else None,
        device_secret=secret,
    )
    db.add(device)
    await db.commit()
    await db.refresh(device)
    return device


async def reset_onboarding_for_device(db: AsyncSession, device: Device) -> None:
    if not device.chip_id and not device.device_id:
        return

    conditions = []
    if device.chip_id:
        conditions.append(DeviceOnboardingRequest.chip_id == device.chip_id)
    if device.device_id:
        conditions.append(DeviceOnboardingRequest.device_id == device.device_id)

    for condition in conditions:
        result = await db.execute(select(DeviceOnboardingRequest).where(condition))
        for request in result.scalars().all():
            if request.pairing_token_id is not None:
                token_result = await db.execute(
                    select(DevicePairingToken).where(DevicePairingToken.id == request.pairing_token_id)
                )
                token = token_result.scalar_one_or_none()
                if token is not None and token.status in {"pending", "used"}:
                    token.status = "revoked"
                    token.used_at = datetime.now(timezone.utc)
            await db.delete(request)


async def deactivate_device(db: AsyncSession, device_id: str) -> bool:
    result = await db.execute(select(Device).where(Device.device_id == device_id))
    device = result.scalar_one_or_none()
    if device is None:
        return False
    await reset_onboarding_for_device(db, device)
    device.chip_id = None
    device.is_active = False
    await db.commit()
    return True


async def delete_device(db: AsyncSession, device_id: str) -> bool:
    device_result = await db.execute(select(Device).where(Device.device_id == device_id))
    device = device_result.scalar_one_or_none()
    if device is None:
        return False
    await reset_onboarding_for_device(db, device)
    result = await db.execute(delete(Device).where(Device.device_id == device_id))
    await db.commit()
    return bool(result.rowcount)


async def validate_device_credentials(db: AsyncSession, device_id: str, secret: str) -> Device | None:
    result = await db.execute(select(Device).where(Device.device_id == device_id))
    device = result.scalar_one_or_none()
    if device is None or not device.is_active or device.device_secret != secret:
        return None
    return device


async def create_pairing_token(db: AsyncSession, user_id: int | None = None) -> DevicePairingToken:
    token = DevicePairingToken(token=_new_pairing_token(), created_by_user_id=user_id)
    db.add(token)
    await db.commit()
    await db.refresh(token)
    return token


async def list_pairing_tokens(db: AsyncSession) -> list[DevicePairingToken]:
    result = await db.execute(
        select(DevicePairingToken).order_by(DevicePairingToken.created_at.desc())
    )
    return list(result.scalars().all())


async def revoke_pairing_token(db: AsyncSession, token_id: int) -> bool:
    result = await db.execute(select(DevicePairingToken).where(DevicePairingToken.id == token_id))
    token = result.scalar_one_or_none()
    if token is None:
        return False
    if token.status == "active":
        token.status = "revoked"
        await db.commit()
    return True


async def list_onboarding_requests(db: AsyncSession) -> list[DeviceOnboardingRequest]:
    result = await db.execute(
        select(DeviceOnboardingRequest).order_by(
            DeviceOnboardingRequest.status,
            DeviceOnboardingRequest.last_seen_at.desc(),
        )
    )
    return list(result.scalars().all())


async def submit_onboarding_request(
    db: AsyncSession,
    chip_id: str,
    module_name: str,
    pairing_token: str,
) -> dict:
    normalized_chip_id = _normalize_chip_id(chip_id)
    normalized_name = _normalize_module_name(module_name, normalized_chip_id)
    now = datetime.now(timezone.utc)

    request_result = await db.execute(
        select(DeviceOnboardingRequest).where(DeviceOnboardingRequest.chip_id == normalized_chip_id)
    )
    existing_request = request_result.scalar_one_or_none()
    if existing_request is not None:
        token_result = await db.execute(
            select(DevicePairingToken).where(DevicePairingToken.token == pairing_token.strip())
        )
        token = token_result.scalar_one_or_none()
        if token is None:
            return {"status": "rejected", "message": "Pairing token is invalid."}

        if token.id != existing_request.pairing_token_id:
            if existing_request.status in {"approved", "rejected"} and token.status == "active":
                if existing_request.pairing_token_id is not None:
                    old_token_result = await db.execute(
                        select(DevicePairingToken).where(
                            DevicePairingToken.id == existing_request.pairing_token_id
                        )
                    )
                    old_token = old_token_result.scalar_one_or_none()
                    if old_token is not None and old_token.status in {"pending", "used"}:
                        old_token.status = "revoked"
                        old_token.used_at = now

                existing_request.status = "pending"
                existing_request.device_id = None
                existing_request.pairing_token_id = token.id
                existing_request.first_seen_at = now
                existing_request.approved_at = None
                existing_request.rejected_at = None
                token.status = "pending"
            else:
                return {"status": "rejected", "message": "Pairing token is invalid."}

        existing_request.last_seen_at = now
        existing_request.module_name = normalized_name
        await db.commit()

        if existing_request.status == "approved" and existing_request.device_id:
            device_result = await db.execute(
                select(Device).where(Device.device_id == existing_request.device_id)
            )
            device = device_result.scalar_one_or_none()
            if device is not None and device.is_active:
                return {
                    "status": "approved",
                    "device_id": device.device_id,
                    "device_secret": device.device_secret,
                    "name": device.name,
                }

        if existing_request.status == "rejected":
            return {"status": "rejected", "message": "Device request was rejected."}

        return {"status": "pending"}

    token_result = await db.execute(
        select(DevicePairingToken).where(DevicePairingToken.token == pairing_token.strip())
    )
    token = token_result.scalar_one_or_none()
    if token is None or token.status != "active":
        return {"status": "rejected", "message": "Pairing token is invalid."}

    token.status = "pending"
    request = DeviceOnboardingRequest(
        chip_id=normalized_chip_id,
        module_name=normalized_name,
        pairing_token_id=token.id,
        first_seen_at=now,
        last_seen_at=now,
    )
    db.add(request)
    await db.commit()
    return {"status": "pending"}


async def approve_onboarding_request(db: AsyncSession, request_id: int) -> tuple[bool, Device | None]:
    result = await db.execute(select(DeviceOnboardingRequest).where(DeviceOnboardingRequest.id == request_id))
    request = result.scalar_one_or_none()
    if request is None or request.status != "pending":
        return False, None

    existing_device_result = await db.execute(select(Device).where(Device.chip_id == request.chip_id))
    existing_device = existing_device_result.scalar_one_or_none()
    if existing_device is not None:
        request.status = "approved"
        request.device_id = existing_device.device_id
        request.approved_at = datetime.now(timezone.utc)
        await db.commit()
        return True, existing_device

    device = await create_device(db, request.module_name, chip_id=request.chip_id)
    request.status = "approved"
    request.device_id = device.device_id
    request.approved_at = datetime.now(timezone.utc)

    if request.pairing_token_id is not None:
        token_result = await db.execute(
            select(DevicePairingToken).where(DevicePairingToken.id == request.pairing_token_id)
        )
        token = token_result.scalar_one_or_none()
        if token is not None:
            token.status = "used"
            token.used_at = datetime.now(timezone.utc)

    await db.commit()
    await db.refresh(device)
    return True, device


async def reject_onboarding_request(db: AsyncSession, request_id: int) -> bool:
    result = await db.execute(select(DeviceOnboardingRequest).where(DeviceOnboardingRequest.id == request_id))
    request = result.scalar_one_or_none()
    if request is None or request.status != "pending":
        return False

    request.status = "rejected"
    request.rejected_at = datetime.now(timezone.utc)
    if request.pairing_token_id is not None:
        token_result = await db.execute(
            select(DevicePairingToken).where(DevicePairingToken.id == request.pairing_token_id)
        )
        token = token_result.scalar_one_or_none()
        if token is not None:
            token.status = "revoked"
            token.used_at = datetime.now(timezone.utc)

    await db.commit()
    return True
