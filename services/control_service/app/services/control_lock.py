from datetime import datetime, timedelta, timezone


LOCK_TIMEOUT_SECONDS = 20
control_locks: dict[str, dict] = {}


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _is_expired(lock: dict) -> bool:
    last_seen_raw = lock.get("last_heartbeat_at") or lock.get("claimed_at")
    if not last_seen_raw:
        return True
    try:
        last_seen = datetime.fromisoformat(last_seen_raw)
    except ValueError:
        return True
    return (_now() - last_seen) > timedelta(seconds=LOCK_TIMEOUT_SECONDS)


def cleanup_expired_locks() -> None:
    expired = [device_id for device_id, lock in control_locks.items() if _is_expired(lock)]
    for device_id in expired:
        control_locks.pop(device_id, None)


def get_lock(device_id: str) -> dict | None:
    cleanup_expired_locks()
    return control_locks.get(device_id)


def claim_lock(device_id: str, user: dict) -> tuple[bool, dict]:
    cleanup_expired_locks()
    existing = control_locks.get(device_id)
    if existing and existing.get("user_id") != user.get("user_id"):
        return False, existing

    now_iso = _now().isoformat()
    lock = {
        "device_id": device_id,
        "user_id": user.get("user_id"),
        "username": user.get("username"),
        "claimed_at": existing.get("claimed_at", now_iso) if existing else now_iso,
        "last_heartbeat_at": now_iso,
    }
    control_locks[device_id] = lock
    return True, lock


def release_lock(device_id: str, user: dict, *, force: bool = False) -> bool:
    existing = get_lock(device_id)
    if not existing:
        return True
    if force or existing.get("user_id") == user.get("user_id"):
        control_locks.pop(device_id, None)
        return True
    return False


def heartbeat_lock(device_id: str, user: dict) -> tuple[bool, dict | None]:
    existing = get_lock(device_id)
    if not existing or existing.get("user_id") != user.get("user_id"):
        return False, existing
    existing["last_heartbeat_at"] = _now().isoformat()
    return True, existing
