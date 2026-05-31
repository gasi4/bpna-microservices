from typing import Any

from pydantic import BaseModel


class CommandRequest(BaseModel):
    device_id: str = "bpna-01"
    command: str
    left_power: int | None = None
    right_power: int | None = None
    extra_type: str | None = None
    value: float | None = None
    extra_value: float | None = None
    enabled: bool | None = None

    def websocket_payload(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "type": "command",
            "command": self.command,
        }
        if self.left_power is not None:
            payload["left_power"] = max(-100, min(100, int(self.left_power)))
        if self.right_power is not None:
            payload["right_power"] = max(-100, min(100, int(self.right_power)))
        if self.extra_type is not None:
            payload["extra_type"] = self.extra_type
        if self.value is not None:
            payload["value"] = self.value
        if self.extra_value is not None:
            payload["extra_value"] = self.extra_value
        if self.enabled is not None:
            payload["enabled"] = self.enabled
        return payload
