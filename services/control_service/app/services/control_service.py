from app.core.device_client import dispatch_command
from app.core.wifi_client import notify_scan_step
from app.schemas.command import CommandCreate, CommandResponse
from app.services.autopilot_state import autopilot_state, set_autopilot


async def send_manual_command(data: CommandCreate) -> CommandResponse:
    if autopilot_state["enabled"]:
        return CommandResponse(
            success=False,
            command=data.command.value,
            message="Autopilot is active. Disable autopilot before manual control.",
        )

    success = await dispatch_command(data.command.value)
    if success:
        await notify_scan_step(data.command.value)
    return CommandResponse(
        success=success,
        command=data.command.value,
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
