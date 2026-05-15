import asyncio
from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import SessionLocal
from app.core.device_client import get_device_state, send_device_command
from app.services.state import get_device_state as get_scan_state
from app.services.wifi_service import clear_measurements, save_measurement_payload
from app.services.websocket_service import broadcast_event


TURN_LEFT = {
    "east": "north",
    "north": "west",
    "west": "south",
    "south": "east",
}
TURN_RIGHT = {
    "east": "south",
    "south": "west",
    "west": "north",
    "north": "east",
}
MOVE_DELTA = {
    "east": (1, 0),
    "west": (-1, 0),
    "south": (0, 1),
    "north": (0, -1),
}
COMMAND_SETTLE_SECONDS = 0.45


def get_scan_status_payload(device_id: str) -> dict:
    state = get_scan_state(device_id)
    return {
        "type": "scan_status",
        "device_id": device_id,
        "running": state.scan_running,
        "mode": state.scan_mode,
        "autopilot": state.scan_mode == "autopilot",
        "session_id": state.scan_session_id,
        "width": state.scan_width,
        "height": state.scan_height,
        "step_cm": state.scan_step_cm,
        "x": state.current_x,
        "y": state.current_y,
        "heading": state.heading,
    }


async def broadcast_scan_status(device_id: str) -> None:
    await broadcast_event(device_id, get_scan_status_payload(device_id))


def append_track(device_id: str, command: str, *, avoiding: bool = False) -> None:
    state = get_scan_state(device_id)
    state.drone_track.append(
        {
            "device_id": device_id,
            "x": state.current_x,
            "y": state.current_y,
            "command": command,
            "avoiding": avoiding,
            "timestamp": datetime.utcnow().isoformat(),
            "heading": state.heading,
        }
    )


def reset_scan_state(device_id: str, width: int, height: int, step_cm: int) -> None:
    state = get_scan_state(device_id)
    state.scan_running = True
    state.scan_mode = "manual"
    state.scan_session_id = datetime.utcnow().strftime(f"{device_id}-%Y%m%d-%H%M%S")
    state.scan_width = width
    state.scan_height = height
    state.scan_step_cm = step_cm
    state.current_x = 0
    state.current_y = 0
    state.heading = "east"
    state.row_direction = 1
    state.drone_track.clear()


async def record_current_measurement(
    db: AsyncSession,
    device_id: str,
    *,
    avoiding: bool = False,
) -> dict | None:
    state = get_scan_state(device_id)
    device_state = await get_device_state(device_id)
    telemetry = device_state.get("last_data") or {}
    if not telemetry:
        return None

    rssi = telemetry.get("wifi_rssi_dbm")
    if rssi is None:
        return None

    payload = {
        "device_id": device_id,
        "x": state.current_x,
        "y": state.current_y,
        "rssi": int(rssi),
        "step_cm": state.scan_step_cm,
        "session_id": state.scan_session_id,
    }
    await save_measurement_payload(db, payload)
    append_track(device_id, "measure", avoiding=avoiding)
    await broadcast_scan_status(device_id)
    return payload


def move_position(device_id: str, command: str) -> bool:
    state = get_scan_state(device_id)
    if command == "left-forward":
        state.heading = TURN_LEFT[state.heading]
        return False
    if command == "right-forward":
        state.heading = TURN_RIGHT[state.heading]
        return False
    if command not in {"forward", "backward"}:
        return False

    dx, dy = MOVE_DELTA[state.heading]
    if command == "backward":
        dx *= -1
        dy *= -1

    next_x = max(0, min(state.scan_width - 1, state.current_x + dx))
    next_y = max(0, min(state.scan_height - 1, state.current_y + dy))
    moved = next_x != state.current_x or next_y != state.current_y
    state.current_x = next_x
    state.current_y = next_y
    return moved


async def process_scan_step(
    db: AsyncSession,
    device_id: str,
    command: str,
    *,
    source: str,
    avoiding: bool = False,
) -> dict:
    state = get_scan_state(device_id)
    if not state.scan_running:
        return {"status": "ignored", "reason": "scan_not_running"}
    if source == "manual" and state.scan_mode != "manual":
        return {"status": "ignored", "reason": "manual_disabled_in_autopilot"}

    if command == "stop":
        append_track(device_id, "stop", avoiding=avoiding)
        await broadcast_scan_status(device_id)
        return {"status": "ok", "moved": False}

    moved = move_position(device_id, command)
    append_track(device_id, command, avoiding=avoiding)
    if moved:
        await record_current_measurement(db, device_id, avoiding=avoiding)
    else:
        await broadcast_scan_status(device_id)
    return {"status": "ok", "moved": moved}


def has_front_obstacle(device_state: dict) -> bool:
    detection = device_state.get("last_detection") or {}
    boxes = detection.get("boxes") or []
    frame_width = max(1, int(detection.get("frame_width") or 0))
    frame_height = max(1, int(detection.get("frame_height") or 0))
    if not boxes or not frame_width or not frame_height:
        return False

    for box in boxes:
        x1 = box.get("x1", 0)
        x2 = box.get("x2", 0)
        y1 = box.get("y1", 0)
        y2 = box.get("y2", 0)
        distance = box.get("distance_cm")
        center_x = (x1 + x2) / 2
        width_ratio = (x2 - x1) / frame_width
        height_ratio = (y2 - y1) / frame_height
        in_center = 0.3 <= center_x / frame_width <= 0.7
        large_enough = width_ratio >= 0.18 or height_ratio >= 0.22
        close_enough = isinstance(distance, (int, float)) and distance <= 140
        if in_center and (large_enough or close_enough):
            return True
    return False


async def execute_command(device_id: str, command: str) -> bool:
    ok = await send_device_command(device_id, command)
    await asyncio.sleep(COMMAND_SETTLE_SECONDS)
    return ok


async def turn_and_track(db: AsyncSession, device_id: str, command: str, *, avoiding: bool = False) -> bool:
    if not await execute_command(device_id, command):
        return False
    await process_scan_step(db, device_id, command, source="autopilot", avoiding=avoiding)
    return True


async def forward_and_track(db: AsyncSession, device_id: str, *, avoiding: bool = False) -> bool:
    if not await execute_command(device_id, "forward"):
        return False
    await process_scan_step(db, device_id, "forward", source="autopilot", avoiding=avoiding)
    return True


async def sidestep_obstacle(db: AsyncSession, device_id: str) -> bool:
    state = get_scan_state(device_id)
    if state.current_y >= state.scan_height - 1:
        return False

    turn_cmd = "right-forward" if state.row_direction == 1 else "left-forward"
    reverse_turn_cmd = "left-forward" if state.row_direction == 1 else "right-forward"
    sequence = [
        turn_cmd,
        "forward",
        reverse_turn_cmd,
        "forward",
        reverse_turn_cmd,
        "forward",
        turn_cmd,
    ]

    for command in sequence:
        if command == "forward":
            if not await forward_and_track(db, device_id, avoiding=True):
                return False
        else:
            if not await turn_and_track(db, device_id, command, avoiding=True):
                return False
    return True


async def maybe_avoid_obstacle(db: AsyncSession, device_id: str) -> bool:
    device_state = await get_device_state(device_id)
    if not has_front_obstacle(device_state):
        return True

    await broadcast_event(
        device_id,
        {
            "type": "scan_notice",
            "device_id": device_id,
            "level": "warning",
            "message": "?????????? ???????????, ???????? ??????",
        },
    )
    return await sidestep_obstacle(db, device_id)


async def run_snake_scan(device_id: str) -> None:
    completed = False
    try:
        async with SessionLocal() as db:
            while True:
                state = get_scan_state(device_id)
                if not state.scan_running or state.scan_mode != "autopilot":
                    break

                can_continue_row = (
                    state.row_direction == 1 and state.current_x < state.scan_width - 1
                ) or (
                    state.row_direction == -1 and state.current_x > 0
                )

                if can_continue_row:
                    if not await maybe_avoid_obstacle(db, device_id):
                        break
                    if not await forward_and_track(db, device_id):
                        break
                    continue

                if state.current_y >= state.scan_height - 1:
                    completed = True
                    break

                turn_cmd = "right-forward" if state.row_direction == 1 else "left-forward"
                if not await turn_and_track(db, device_id, turn_cmd):
                    break
                if not await forward_and_track(db, device_id):
                    break
                if not await turn_and_track(db, device_id, turn_cmd):
                    break
                state.row_direction *= -1

    except asyncio.CancelledError:
        raise
    finally:
        state = get_scan_state(device_id)
        current_task = asyncio.current_task()
        if state.scan_task is current_task:
            state.scan_task = None

        if state.scan_running and state.scan_mode == "manual":
            await send_device_command(device_id, "stop")
            await broadcast_scan_status(device_id)
        else:
            state.scan_running = False
            state.scan_mode = "manual"
            await send_device_command(device_id, "stop")
            await broadcast_scan_status(device_id)
            await broadcast_event(device_id, {"type": "scan_complete", "device_id": device_id, "completed": completed})


async def set_scan_mode(device_id: str, mode: str) -> dict:
    state = get_scan_state(device_id)
    mode = mode if mode in {"manual", "autopilot"} else "manual"
    if not state.scan_running:
        return {"status": "error", "message": "??????? ????????? ????????????"}

    if mode == state.scan_mode:
        payload = get_scan_status_payload(device_id)
        payload["status"] = "unchanged"
        return payload

    state.scan_mode = mode

    if mode == "autopilot":
        if state.scan_task is None or state.scan_task.done():
            state.scan_task = asyncio.create_task(run_snake_scan(device_id))
        await broadcast_event(
            device_id,
            {"type": "scan_notice", "device_id": device_id, "level": "info", "message": "?????????? ???????"},
        )
    else:
        if state.scan_task and not state.scan_task.done():
            state.scan_task.cancel()
        state.scan_task = None
        await send_device_command(device_id, "stop")
        await broadcast_event(
            device_id,
            {"type": "scan_notice", "device_id": device_id, "level": "info", "message": "?????????? ????????, ???????? ?????? ??????????"},
        )

    await broadcast_scan_status(device_id)
    payload = get_scan_status_payload(device_id)
    payload["status"] = "mode_updated"
    return payload


async def start_scan(
    db: AsyncSession,
    device_id: str,
    width: int,
    height: int,
    step_cm: int,
    mode: str,
) -> dict:
    state = get_scan_state(device_id)
    if state.scan_task and not state.scan_task.done():
        state.scan_task.cancel()
        state.scan_task = None

    reset_scan_state(device_id, width, height, step_cm)
    await clear_measurements(db, device_id)
    await send_device_command(device_id, "stop")
    await record_current_measurement(db, device_id)
    await broadcast_scan_status(device_id)

    payload = get_scan_status_payload(device_id)
    payload["status"] = "scan_started"

    if mode == "autopilot":
        return await set_scan_mode(device_id, "autopilot")

    return payload


async def stop_scan(device_id: str) -> dict:
    state = get_scan_state(device_id)
    state.scan_running = False
    state.scan_mode = "manual"
    if state.scan_task and not state.scan_task.done():
        state.scan_task.cancel()
    state.scan_task = None
    await send_device_command(device_id, "stop")
    await broadcast_scan_status(device_id)
    payload = get_scan_status_payload(device_id)
    payload["status"] = "scan_stopped"
    return payload
