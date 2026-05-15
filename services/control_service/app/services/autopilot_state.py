autopilot_by_device: dict[str, dict] = {}


def get_autopilot_state(device_id: str) -> dict:
    return autopilot_by_device.setdefault(
        device_id,
        {
            "enabled": False,
            "target_id": None,
            "target_label": None,
            "last_command": "stop",
        },
    )


def set_autopilot(
    device_id: str,
    enabled: bool,
    target_id: int | None,
    target_label: str | None,
) -> dict:
    state = get_autopilot_state(device_id)
    state.update(
        {
            "enabled": enabled,
            "target_id": target_id,
            "target_label": target_label,
            "last_command": "stop",
        }
    )
    return state
