import asyncio
from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import SessionLocal
from app.core.device_client import get_device_state, send_device_command
from app.services import state
from app.services.wifi_service import clear_measurements, save_measurement_payload
from app.services.websocket_service import broadcast_event


TURN_LEFT = {
    'east': 'north',
    'north': 'west',
    'west': 'south',
    'south': 'east',
}
TURN_RIGHT = {
    'east': 'south',
    'south': 'west',
    'west': 'north',
    'north': 'east',
}
MOVE_DELTA = {
    'east': (1, 0),
    'west': (-1, 0),
    'south': (0, 1),
    'north': (0, -1),
}
COMMAND_SETTLE_SECONDS = 0.45


def get_scan_status_payload() -> dict:
    return {
        'type': 'scan_status',
        'running': state.scan_running,
        'mode': state.scan_mode,
        'autopilot': state.scan_mode == 'autopilot',
        'session_id': state.scan_session_id,
        'width': state.scan_width,
        'height': state.scan_height,
        'step_cm': state.scan_step_cm,
        'x': state.current_x,
        'y': state.current_y,
        'heading': state.heading,
    }


async def broadcast_scan_status() -> None:
    await broadcast_event(get_scan_status_payload())


def append_track(command: str, *, avoiding: bool = False) -> None:
    state.drone_track.append(
        {
            'x': state.current_x,
            'y': state.current_y,
            'command': command,
            'avoiding': avoiding,
            'timestamp': datetime.utcnow().isoformat(),
            'heading': state.heading,
        }
    )


def reset_scan_state(width: int, height: int, step_cm: int) -> None:
    state.scan_running = True
    state.scan_mode = 'manual'
    state.scan_session_id = datetime.utcnow().strftime('scan-%Y%m%d-%H%M%S')
    state.scan_width = width
    state.scan_height = height
    state.scan_step_cm = step_cm
    state.current_x = 0
    state.current_y = 0
    state.heading = 'east'
    state.row_direction = 1
    state.drone_track.clear()


async def record_current_measurement(
    db: AsyncSession,
    *,
    avoiding: bool = False,
) -> dict | None:
    device_state = await get_device_state()
    telemetry = device_state.get('last_data') or {}
    if not telemetry:
        return None

    rssi = telemetry.get('wifi_rssi_dbm')
    if rssi is None:
        return None

    payload = {
        'x': state.current_x,
        'y': state.current_y,
        'rssi': int(rssi),
        'step_cm': state.scan_step_cm,
        'session_id': state.scan_session_id,
    }
    await save_measurement_payload(db, payload)
    append_track('measure', avoiding=avoiding)
    await broadcast_scan_status()
    return payload


def move_position(command: str) -> bool:
    if command == 'left-forward':
        state.heading = TURN_LEFT[state.heading]
        return False
    if command == 'right-forward':
        state.heading = TURN_RIGHT[state.heading]
        return False
    if command not in {'forward', 'backward'}:
        return False

    dx, dy = MOVE_DELTA[state.heading]
    if command == 'backward':
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
    command: str,
    *,
    source: str,
    avoiding: bool = False,
) -> dict:
    if not state.scan_running:
        return {'status': 'ignored', 'reason': 'scan_not_running'}
    if source == 'manual' and state.scan_mode != 'manual':
        return {'status': 'ignored', 'reason': 'manual_disabled_in_autopilot'}

    if command == 'stop':
        append_track('stop', avoiding=avoiding)
        await broadcast_scan_status()
        return {'status': 'ok', 'moved': False}

    moved = move_position(command)
    append_track(command, avoiding=avoiding)
    if moved:
        await record_current_measurement(db, avoiding=avoiding)
    else:
        await broadcast_scan_status()
    return {'status': 'ok', 'moved': moved}


def has_front_obstacle(device_state: dict) -> bool:
    detection = device_state.get('last_detection') or {}
    boxes = detection.get('boxes') or []
    frame_width = max(1, int(detection.get('frame_width') or 0))
    frame_height = max(1, int(detection.get('frame_height') or 0))
    if not boxes or not frame_width or not frame_height:
        return False

    for box in boxes:
        x1 = box.get('x1', 0)
        x2 = box.get('x2', 0)
        y1 = box.get('y1', 0)
        y2 = box.get('y2', 0)
        distance = box.get('distance_cm')
        center_x = (x1 + x2) / 2
        width_ratio = (x2 - x1) / frame_width
        height_ratio = (y2 - y1) / frame_height
        in_center = 0.3 <= center_x / frame_width <= 0.7
        large_enough = width_ratio >= 0.18 or height_ratio >= 0.22
        close_enough = isinstance(distance, (int, float)) and distance <= 140
        if in_center and (large_enough or close_enough):
            return True
    return False


async def execute_command(command: str) -> bool:
    ok = await send_device_command(command)
    await asyncio.sleep(COMMAND_SETTLE_SECONDS)
    return ok


async def turn_and_track(db: AsyncSession, command: str, *, avoiding: bool = False) -> bool:
    if not await execute_command(command):
        return False
    await process_scan_step(db, command, source='autopilot', avoiding=avoiding)
    return True


async def forward_and_track(db: AsyncSession, *, avoiding: bool = False) -> bool:
    if not await execute_command('forward'):
        return False
    await process_scan_step(db, 'forward', source='autopilot', avoiding=avoiding)
    return True


async def sidestep_obstacle(db: AsyncSession) -> bool:
    if state.current_y >= state.scan_height - 1:
        return False

    turn_cmd = 'right-forward' if state.row_direction == 1 else 'left-forward'
    reverse_turn_cmd = 'left-forward' if state.row_direction == 1 else 'right-forward'
    sequence = [
        turn_cmd,
        'forward',
        reverse_turn_cmd,
        'forward',
        reverse_turn_cmd,
        'forward',
        turn_cmd,
    ]

    for command in sequence:
        if command == 'forward':
            if not await forward_and_track(db, avoiding=True):
                return False
        else:
            if not await turn_and_track(db, command, avoiding=True):
                return False
    return True


async def maybe_avoid_obstacle(db: AsyncSession) -> bool:
    device_state = await get_device_state()
    if not has_front_obstacle(device_state):
        return True

    await broadcast_event(
        {
            'type': 'scan_notice',
            'level': 'warning',
            'message': 'Обнаружено препятствие, выполняю объезд',
        }
    )
    return await sidestep_obstacle(db)


async def run_snake_scan() -> None:
    completed = False
    try:
        async with SessionLocal() as db:
            while state.scan_running and state.scan_mode == 'autopilot':
                can_continue_row = (
                    state.row_direction == 1 and state.current_x < state.scan_width - 1
                ) or (
                    state.row_direction == -1 and state.current_x > 0
                )

                if can_continue_row:
                    if not await maybe_avoid_obstacle(db):
                        break
                    if not await forward_and_track(db):
                        break
                    continue

                if state.current_y >= state.scan_height - 1:
                    completed = True
                    break

                turn_cmd = 'right-forward' if state.row_direction == 1 else 'left-forward'
                if not await turn_and_track(db, turn_cmd):
                    break
                if not await forward_and_track(db):
                    break
                if not await turn_and_track(db, turn_cmd):
                    break
                state.row_direction *= -1

    except asyncio.CancelledError:
        raise
    finally:
        current_task = asyncio.current_task()
        if state.scan_task is current_task:
            state.scan_task = None

        if state.scan_running and state.scan_mode == 'manual':
            await send_device_command('stop')
            await broadcast_scan_status()
        else:
            state.scan_running = False
            state.scan_mode = 'manual'
            await send_device_command('stop')
            await broadcast_scan_status()
            await broadcast_event({'type': 'scan_complete', 'completed': completed})


async def set_scan_mode(mode: str) -> dict:
    mode = mode if mode in {'manual', 'autopilot'} else 'manual'
    if not state.scan_running:
        return {'status': 'error', 'message': 'Сначала запустите сканирование'}

    if mode == state.scan_mode:
        payload = get_scan_status_payload()
        payload['status'] = 'unchanged'
        return payload

    state.scan_mode = mode

    if mode == 'autopilot':
        if state.scan_task is None or state.scan_task.done():
            state.scan_task = asyncio.create_task(run_snake_scan())
        await broadcast_event(
            {'type': 'scan_notice', 'level': 'info', 'message': 'Автозмейка включена'}
        )
    else:
        if state.scan_task and not state.scan_task.done():
            state.scan_task.cancel()
        state.scan_task = None
        await send_device_command('stop')
        await broadcast_event(
            {'type': 'scan_notice', 'level': 'info', 'message': 'Автозмейка выключена, доступно ручное управление'}
        )

    await broadcast_scan_status()
    payload = get_scan_status_payload()
    payload['status'] = 'mode_updated'
    return payload


async def start_scan(
    db: AsyncSession,
    width: int,
    height: int,
    step_cm: int,
    mode: str,
) -> dict:
    if state.scan_task and not state.scan_task.done():
        state.scan_task.cancel()
        state.scan_task = None

    reset_scan_state(width, height, step_cm)
    await clear_measurements(db)
    await send_device_command('stop')
    await record_current_measurement(db)
    await broadcast_scan_status()

    payload = get_scan_status_payload()
    payload['status'] = 'scan_started'

    if mode == 'autopilot':
        return await set_scan_mode('autopilot')

    return payload


async def stop_scan() -> dict:
    state.scan_running = False
    state.scan_mode = 'manual'
    if state.scan_task and not state.scan_task.done():
        state.scan_task.cancel()
    state.scan_task = None
    await send_device_command('stop')
    await broadcast_scan_status()
    payload = get_scan_status_payload()
    payload['status'] = 'scan_stopped'
    return payload
