from pydantic import BaseModel


class CommandRequest(BaseModel):
    device_id: str = "bpna-01"
    command: str
