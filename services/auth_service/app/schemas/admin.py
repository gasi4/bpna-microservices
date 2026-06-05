from datetime import datetime

from pydantic import BaseModel, Field


class UserCreate(BaseModel):
    username: str
    password: str
    role: str = Field(default="operator")


class UserOut(BaseModel):
    id: int
    username: str
    role: str
    is_active: bool
    created_at: datetime | None = None


class DeviceCreate(BaseModel):
    name: str
    device_id: str | None = None


class DeviceOut(BaseModel):
    id: int
    device_id: str
    chip_id: str | None = None
    name: str
    is_active: bool
    created_at: datetime | None = None


class DeviceAdminOut(DeviceOut):
    device_secret: str


class DeviceCreateResponse(DeviceOut):
    device_secret: str


class DeviceValidateRequest(BaseModel):
    device_id: str
    secret: str


class DeviceValidateResponse(BaseModel):
    id: int
    device_id: str
    name: str
    is_active: bool


class DevicePairingTokenOut(BaseModel):
    id: int
    token: str
    status: str
    created_by_user_id: int | None = None
    created_at: datetime | None = None
    used_at: datetime | None = None


class DeviceOnboardingRequestIn(BaseModel):
    chip_id: str
    module_name: str
    pairing_token: str


class DeviceOnboardingResponse(BaseModel):
    status: str
    retry_after_seconds: int = 5
    device_id: str | None = None
    device_secret: str | None = None
    name: str | None = None
    message: str | None = None


class DeviceOnboardingRequestOut(BaseModel):
    id: int
    chip_id: str
    module_name: str
    status: str
    device_id: str | None = None
    pairing_token_id: int | None = None
    first_seen_at: datetime | None = None
    last_seen_at: datetime | None = None
    approved_at: datetime | None = None
    rejected_at: datetime | None = None
