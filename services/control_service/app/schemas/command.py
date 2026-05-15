from enum import Enum

from pydantic import BaseModel


class CommandType(str, Enum):
    forward = "forward"
    backward = "backward"
    left_forward = "left-forward"
    right_forward = "right-forward"
    stop = "stop"
    led_on = "led-on"
    led_off = "led-off"
    led_toggle = "led-toggle"
    flash_on = "flash-on"
    flash_off = "flash-off"
    flash_toggle = "flash-toggle"
    flashlight_on = "flashlight-on"
    flashlight_off = "flashlight-off"
    flashlight_toggle = "flashlight-toggle"
    light_on = "light-on"
    light_off = "light-off"
    light_toggle = "light-toggle"


class CommandCreate(BaseModel):
    command: CommandType


class CommandResponse(BaseModel):
    success: bool
    command: str
    message: str
