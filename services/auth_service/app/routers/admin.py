from fastapi import APIRouter, Depends, Header, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import decode_token
from app.schemas.admin import (
    DeviceCreate,
    DeviceAdminOut,
    DeviceCreateResponse,
    DeviceOut,
    DeviceValidateRequest,
    DeviceValidateResponse,
    UserCreate,
    UserOut,
)
from app.schemas.auth import TokenUser
from app.services.auth_service import (
    create_device,
    create_user,
    deactivate_device,
    deactivate_user,
    delete_device,
    delete_user,
    list_devices,
    list_users,
    validate_device_credentials,
)


router = APIRouter()


def _require_token_user(authorization: str | None) -> TokenUser:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Bearer token is required")
    return decode_token(authorization.split(" ", 1)[1])


async def require_admin(authorization: str | None = Header(default=None)) -> TokenUser:
    user = _require_token_user(authorization)
    if user.role != "admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin role is required")
    return user


async def require_auth_user(authorization: str | None = Header(default=None)) -> TokenUser:
    return _require_token_user(authorization)


@router.get("/users", response_model=list[UserOut])
async def get_users(
    db: AsyncSession = Depends(get_db),
    user: TokenUser = Depends(require_admin),
):
    rows = await list_users(db)
    return [
        UserOut(
            id=item.id,
            username=item.username,
            role=item.role,
            is_active=item.is_active,
            created_at=item.created_at,
        )
        for item in rows
    ]


@router.post("/users", response_model=UserOut)
async def add_user(
    data: UserCreate,
    db: AsyncSession = Depends(get_db),
    user: TokenUser = Depends(require_admin),
):
    item = await create_user(db, data.username, data.password, data.role)
    return UserOut(
        id=item.id,
        username=item.username,
        role=item.role,
        is_active=item.is_active,
        created_at=item.created_at,
    )


@router.delete("/users/{user_id}")
async def remove_user(
    user_id: int,
    db: AsyncSession = Depends(get_db),
    user: TokenUser = Depends(require_admin),
):
    ok = await deactivate_user(db, user_id)
    if not ok:
        raise HTTPException(status_code=404, detail="User not found")
    return {"success": True}


@router.delete("/users/{user_id}/purge")
async def purge_user(
    user_id: int,
    db: AsyncSession = Depends(get_db),
    user: TokenUser = Depends(require_admin),
):
    if user.user_id == user_id:
        raise HTTPException(status_code=400, detail="Current admin account cannot be deleted")
    ok = await delete_user(db, user_id)
    if not ok:
        raise HTTPException(status_code=404, detail="User not found")
    return {"success": True}


@router.get("/devices", response_model=list[DeviceOut])
async def get_devices(
    db: AsyncSession = Depends(get_db),
    user: TokenUser = Depends(require_auth_user),
):
    rows = await list_devices(db)
    return [
        DeviceOut(
            id=item.id,
            device_id=item.device_id,
            name=item.name,
            is_active=item.is_active,
            created_at=item.created_at,
        )
        for item in rows
    ]


@router.get("/admin/devices", response_model=list[DeviceAdminOut])
async def get_admin_devices(
    db: AsyncSession = Depends(get_db),
    user: TokenUser = Depends(require_admin),
):
    rows = await list_devices(db, include_inactive=True)
    return [
        DeviceAdminOut(
            id=item.id,
            device_id=item.device_id,
            name=item.name,
            is_active=item.is_active,
            created_at=item.created_at,
            device_secret=item.device_secret,
        )
        for item in rows
    ]


@router.post("/devices", response_model=DeviceCreateResponse)
async def add_device(
    data: DeviceCreate,
    db: AsyncSession = Depends(get_db),
    user: TokenUser = Depends(require_admin),
):
    item = await create_device(db, data.name, data.device_id)
    return DeviceCreateResponse(
        id=item.id,
        device_id=item.device_id,
        name=item.name,
        is_active=item.is_active,
        created_at=item.created_at,
        device_secret=item.device_secret,
    )


@router.post("/admin/devices", response_model=DeviceCreateResponse)
async def add_admin_device(
    data: DeviceCreate,
    db: AsyncSession = Depends(get_db),
    user: TokenUser = Depends(require_admin),
):
    return await add_device(data, db, user)


@router.delete("/devices/{device_id}")
async def remove_device(
    device_id: str,
    db: AsyncSession = Depends(get_db),
    user: TokenUser = Depends(require_admin),
):
    ok = await deactivate_device(db, device_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Device not found")
    return {"success": True}


@router.delete("/admin/devices/{device_id}")
async def remove_admin_device(
    device_id: str,
    db: AsyncSession = Depends(get_db),
    user: TokenUser = Depends(require_admin),
):
    return await remove_device(device_id, db, user)


@router.delete("/admin/devices/{device_id}/purge")
async def purge_device(
    device_id: str,
    db: AsyncSession = Depends(get_db),
    user: TokenUser = Depends(require_admin),
):
    ok = await delete_device(db, device_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Device not found")
    return {"success": True}


@router.post("/devices/validate", response_model=DeviceValidateResponse)
async def validate_device(
    data: DeviceValidateRequest,
    db: AsyncSession = Depends(get_db),
):
    device = await validate_device_credentials(db, data.device_id, data.secret)
    if device is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid device credentials")
    return DeviceValidateResponse(
        id=device.id,
        device_id=device.device_id,
        name=device.name,
        is_active=device.is_active,
    )
