from typing import Any

from pydantic import BaseModel, field_validator, model_validator


ALLOWED_COMMANDS = {
    "forward",
    "backward",
    "left-forward",
    "right-forward",
    "stop",
    "motor-power",
    "extra-button",
    "extra-toggle-on",
    "extra-toggle-off",
    "extra-slider",
    "led-on",
    "led-off",
    "led-toggle",
    "flash-on",
    "flash-off",
    "flash-toggle",
    "flashlight-on",
    "flashlight-off",
    "flashlight-toggle",
    "light-on",
    "light-off",
    "light-toggle",
}


class CommandCreate(BaseModel):
    device_id: str = "bpna-01"
    command: str
    left_power: int | None = None
    right_power: int | None = None
    extra_type: str | None = None
    value: float | None = None
    extra_value: float | None = None
    enabled: bool | None = None

    @field_validator("command")
    @classmethod
    def validate_command(cls, value: str) -> str:
        command = value.strip().lower()
        if command not in ALLOWED_COMMANDS:
            raise ValueError(f"Unsupported command: {value}")
        return command

    @model_validator(mode="after")
    def validate_payload(self) -> "CommandCreate":
        if self.command == "motor-power":
            if self.left_power is None or self.right_power is None:
                raise ValueError("motor-power requires left_power and right_power")
            self.left_power = max(-100, min(100, int(self.left_power)))
            self.right_power = max(-100, min(100, int(self.right_power)))
        return self

    def device_payload(self) -> dict[str, Any]:
        payload: dict[str, Any] = {"command": self.command}
        if self.left_power is not None:
            payload["left_power"] = self.left_power
        if self.right_power is not None:
            payload["right_power"] = self.right_power
        if self.extra_type is not None:
            payload["extra_type"] = self.extra_type
        if self.value is not None:
            payload["value"] = self.value
        if self.extra_value is not None:
            payload["extra_value"] = self.extra_value
        if self.enabled is not None:
            payload["enabled"] = self.enabled
        return payload


class CommandResponse(BaseModel):
    success: bool
    command: str
    device_id: str
    message: str
