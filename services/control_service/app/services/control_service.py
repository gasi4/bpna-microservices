from app.core.device_client import dispatch_command
from app.core.wifi_client import notify_scan_step
from app.schemas.command import CommandCreate, CommandResponse
from app.services.autopilot_state import autopilot_state, set_autopilot


MOVEMENT_COMMANDS = {"forward", "backward", "left-forward", "right-forward", "stop"}


async def send_manual_command(data: CommandCreate) -> CommandResponse:
    command = data.command.value
    is_movement_command = command in MOVEMENT_COMMANDS

    if autopilot_state["enabled"] and is_movement_command:
        return CommandResponse(
            success=False,
            command=command,
            message="Autopilot is active. Disable autopilot before manual control.",
        )

    success = await dispatch_command(command)
    if success and is_movement_command:
        await notify_scan_step(command)
    return CommandResponse(
        success=success,
        command=command,
        message="Command sent" if success else "Device is unavailable",
    )


async def toggle_autopilot(
    enabled: bool,
    target_id: int | None,
    target_label: str | None,
) -> dict:
    state = set_autopilot(enabled, target_id, target_label)
    if not enabled:
        await dispatch_command("stop")
    return {"autopilot": enabled, **state}
