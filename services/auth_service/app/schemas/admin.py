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


class DeviceCreate(BaseModel):
    name: str
    device_id: str | None = None


class DeviceOut(BaseModel):
    id: int
    device_id: str
    name: str
    is_active: bool


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
