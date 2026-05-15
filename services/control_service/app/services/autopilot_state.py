autopilot_state: dict = {
    "enabled": False,
    "target_id": None,
    "target_label": None,
    "last_command": "stop",
}


def set_autopilot(
    enabled: bool,
    target_id: int | None,
    target_label: str | None,
) -> dict:
    autopilot_state.update(
        {
            "enabled": enabled,
            "target_id": target_id,
            "target_label": target_label,
            "last_command": "stop",
        }
    )
    return autopilot_state
