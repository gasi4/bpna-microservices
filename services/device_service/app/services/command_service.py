import json

from app.services import state


async def send_command_to_device(command: str) -> bool:
    if state.device_ws is None:
        return False

    try:
        await state.device_ws.send_text(
            json.dumps({"type": "command", "command": command})
        )
        return True
    except Exception:
        state.device_ws = None
        state.device_state["connected"] = False
        return False
