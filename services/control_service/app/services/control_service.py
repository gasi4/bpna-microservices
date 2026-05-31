from app.core.device_client import dispatch_command, get_device_states
from app.core.registry_client import get_registered_devices
from app.core.wifi_client import notify_scan_step
from app.schemas.command import CommandCreate, CommandResponse
from app.services.autopilot_state import get_autopilot_state, set_autopilot
from app.services.control_lock import claim_lock, get_lock, heartbeat_lock, release_lock


MOVEMENT_COMMANDS = {"forward", "backward", "left-forward", "right-forward", "stop", "motor-power"}
SCAN_STEP_COMMANDS = {"forward", "backward", "left-forward", "right-forward", "stop"}


async def send_manual_command(data: CommandCreate, user: dict) -> CommandResponse:
    command = data.command
    device_id = data.device_id
    is_movement_command = command in MOVEMENT_COMMANDS
    lock = get_lock(device_id)

    if not lock or lock.get("user_id") != user.get("user_id"):
        return CommandResponse(
            success=False,
            command=command,
            device_id=device_id,
            message="Control lock is required for this device.",
        )

    autopilot_state = get_autopilot_state(device_id)
    if autopilot_state["enabled"] and is_movement_command:
        return CommandResponse(
            success=False,
            command=command,
            device_id=device_id,
            message="Autopilot is active. Disable autopilot before manual control.",
        )

    success = await dispatch_command(data.device_payload(), device_id)
    if success and command in SCAN_STEP_COMMANDS:
        await notify_scan_step(command, device_id)
    return CommandResponse(
        success=success,
        command=command,
        device_id=device_id,
        message="Command sent" if success else "Device is unavailable",
    )


async def toggle_autopilot(
    device_id: str,
    enabled: bool,
    target_id: int | None,
    target_label: str | None,
    user: dict,
) -> dict:
    lock = get_lock(device_id)
    if not lock or lock.get("user_id") != user.get("user_id"):
        return {"success": False, "message": "Control lock is required.", "device_id": device_id}

    state = set_autopilot(device_id, enabled, target_id, target_label)
    if not enabled:
        await dispatch_command("stop", device_id)
    return {"success": True, "device_id": device_id, "autopilot": enabled, **state}


async def claim_device_control(device_id: str, user: dict) -> dict:
    success, lock = claim_lock(device_id, user)
    if not success:
        return {"success": False, "device_id": device_id, "message": "Device is already busy.", "lock": lock}
    return {"success": True, "device_id": device_id, "lock": lock}


async def release_device_control(device_id: str, user: dict) -> dict:
    success = release_lock(device_id, user)
    if not success:
        return {"success": False, "device_id": device_id, "message": "You do not own the lock."}
    set_autopilot(device_id, False, None, None)
    await dispatch_command("stop", device_id)
    return {"success": True, "device_id": device_id}


async def heartbeat_device_control(device_id: str, user: dict) -> dict:
    success, lock = heartbeat_lock(device_id, user)
    return {"success": success, "device_id": device_id, "lock": lock}


async def list_devices_with_status(authorization: str) -> list[dict]:
    registered = await get_registered_devices(authorization)
    runtime_states = {item.get("device_id"): item for item in await get_device_states()}

    devices = []
    for item in registered:
        device_id = item.get("device_id")
        runtime = runtime_states.get(device_id) or {"connected": False, "last_seen": None, "last_data": None}
        lock = get_lock(device_id)
        if not runtime.get("connected"):
            status = "offline"
        elif lock:
            status = "busy"
        else:
            status = "online"

        devices.append(
            {
                **item,
                "status": status,
                "connected": bool(runtime.get("connected")),
                "last_seen": runtime.get("last_seen"),
                "last_data": runtime.get("last_data"),
                "controller_username": lock.get("username") if lock else None,
                "controller_user_id": lock.get("user_id") if lock else None,
            }
        )
    return devices
