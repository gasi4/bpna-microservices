from enum import Enum

from pydantic import BaseModel


class CommandType(str, Enum):
    forward = "forward"
    backward = "backward"
    left_forward = "left-forward"
    right_forward = "right-forward"
    stop = "stop"


class CommandCreate(BaseModel):
    command: CommandType


class CommandResponse(BaseModel):
    success: bool
    command: str
    message: str
