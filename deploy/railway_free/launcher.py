import os
import signal
import socket
import subprocess
import sys
import time
from pathlib import Path
from urllib.parse import quote_plus, urlparse

ROOT = Path("/opt/bpna")
SERVICES_DIR = ROOT / "services"
RETRY_DELAY_SECONDS = 5.0


def normalize_database_url(url: str | None) -> str | None:
    if not url:
        return url
    url = url.strip().strip('"').strip("'")
    if url.startswith("postgresql+asyncpg://"):
        return url
    if url.startswith("postgres://"):
        return "postgresql+asyncpg://" + url[len("postgres://") :]
    if url.startswith("postgresql://"):
        return "postgresql+asyncpg://" + url[len("postgresql://") :]
    return url


def derive_database_url(env: dict[str, str]) -> str | None:
    database_url = normalize_database_url(env.get("DATABASE_URL"))
    if database_url and "${{" not in database_url and "}}" not in database_url:
        return database_url

    pg_host = env.get("PGHOST")
    pg_port = env.get("PGPORT", "5432")
    pg_user = env.get("PGUSER")
    pg_password = env.get("PGPASSWORD")
    pg_database = env.get("PGDATABASE")

    if all([pg_host, pg_user, pg_password, pg_database]):
        return (
            "postgresql+asyncpg://"
            f"{quote_plus(pg_user)}:{quote_plus(pg_password)}"
            f"@{pg_host}:{pg_port}/{quote_plus(pg_database)}"
        )

    return database_url


def get_database_target(env: dict[str, str]) -> tuple[str, int] | None:
    host = env.get("PGHOST")
    port = env.get("PGPORT")
    if host:
        return host, int(port or "5432")

    database_url = derive_database_url(env)
    if not database_url:
        return None

    parsed = urlparse(database_url)
    if parsed.hostname:
        return parsed.hostname, parsed.port or 5432
    return None


def database_is_reachable(env: dict[str, str]) -> bool:
    target = get_database_target(env)
    if not target:
        return False

    host, port = target
    try:
        with socket.create_connection((host, port), timeout=3):
            return True
    except OSError:
        return False


def build_env(port: int, public: bool = False) -> dict[str, str]:
    env = os.environ.copy()
    env["PORT"] = str(port)
    env["HOSTNAME"] = "0.0.0.0" if public else "127.0.0.1"
    env["AUTH_SERVICE_URL"] = "http://127.0.0.1:8001"
    env["TELEMETRY_SERVICE_URL"] = "http://127.0.0.1:8002"
    env["DEVICE_SERVICE_URL"] = "http://127.0.0.1:8003"
    env["CONTROL_SERVICE_URL"] = "http://127.0.0.1:8004"
    env["WIFI_SERVICE_URL"] = "http://127.0.0.1:8005"
    env["DETECTION_SERVICE_URL"] = "http://127.0.0.1:8006"
    env["DEVICE_WS_URL"] = "ws://127.0.0.1:8003"
    env["WIFI_WS_URL"] = "ws://127.0.0.1:8005"
    database_url = derive_database_url(env)
    if database_url:
        env["DATABASE_URL"] = database_url
    for model_name in ("yolo11n.pt", "yolo11s.pt"):
        model_path = ROOT / model_name
        if model_path.exists():
            env["YOLO_MODEL_PATH"] = str(model_path)
            break
    env.setdefault("YOLO_CONFIG_DIR", "/tmp/Ultralytics")
    return env


SERVICE_SPECS = [
    {
        "name": "auth-service",
        "cwd": SERVICES_DIR / "auth_service",
        "port": 8001,
        "public": False,
        "requires_db": True,
    },
    {
        "name": "telemetry-service",
        "cwd": SERVICES_DIR / "telemetry_service",
        "port": 8002,
        "public": False,
        "requires_db": True,
    },
    {
        "name": "device-service",
        "cwd": SERVICES_DIR / "device_service",
        "port": 8003,
        "public": False,
        "requires_db": False,
    },
    {
        "name": "control-service",
        "cwd": SERVICES_DIR / "control_service",
        "port": 8004,
        "public": False,
        "requires_db": False,
    },
    {
        "name": "wifi-service",
        "cwd": SERVICES_DIR / "wifi_service",
        "port": 8005,
        "public": False,
        "requires_db": True,
    },
    {
        "name": "detection-service",
        "cwd": SERVICES_DIR / "detection_service",
        "port": 8006,
        "public": False,
        "requires_db": False,
    },
    {
        "name": "api-gateway",
        "cwd": SERVICES_DIR / "api_gateway",
        "port": int(os.getenv("PORT", "8000")),
        "public": True,
        "requires_db": False,
    },
]


processes: dict[str, subprocess.Popen[str]] = {}
restart_after: dict[str, float] = {
    spec["name"]: 0.0 for spec in SERVICE_SPECS
}
shutting_down = False
last_db_wait_log = 0.0


def terminate_all() -> None:
    global shutting_down
    if shutting_down:
        return
    shutting_down = True
    for name, process in reversed(list(processes.items())):
        if process.poll() is None:
            print(f"[launcher] stopping {name}...", flush=True)
            process.terminate()
    deadline = time.time() + 10
    for name, process in reversed(list(processes.items())):
        while process.poll() is None and time.time() < deadline:
            time.sleep(0.2)
        if process.poll() is None:
            print(f"[launcher] killing {name}...", flush=True)
            process.kill()


def handle_signal(signum, frame):
    print(f"[launcher] received signal {signum}, shutting down", flush=True)
    terminate_all()
    sys.exit(0)


def start_service(spec: dict) -> None:
    env = build_env(spec["port"], public=spec["public"])
    command = [
        sys.executable,
        "-m",
        "uvicorn",
        "app.main:app",
        "--host",
        "0.0.0.0" if spec["public"] else "127.0.0.1",
        "--port",
        str(spec["port"]),
    ]
    print(
        f"[launcher] starting {spec['name']} on port {spec['port']}",
        flush=True,
    )
    process = subprocess.Popen(command, cwd=str(spec["cwd"]), env=env)
    processes[spec["name"]] = process


signal.signal(signal.SIGINT, handle_signal)
signal.signal(signal.SIGTERM, handle_signal)

spec_by_name = {spec["name"]: spec for spec in SERVICE_SPECS}

while True:
    now = time.time()

    for spec in SERVICE_SPECS:
        name = spec["name"]
        process = processes.get(name)
        if process and process.poll() is None:
            continue

        if process and process.poll() is not None:
            code = process.returncode or 0
            print(f"[launcher] {name} exited with code {code}", flush=True)
            processes.pop(name, None)
            restart_after[name] = now + RETRY_DELAY_SECONDS

        if now < restart_after[name]:
            continue

        env = build_env(spec["port"], public=spec["public"])
        if spec["requires_db"] and not database_is_reachable(env):
            target = get_database_target(env)
            if target:
                if now - last_db_wait_log >= 5:
                    host, port = target
                    print(
                        f"[launcher] waiting for database at {host}:{port} "
                        f"before starting {name}",
                        flush=True,
                    )
                    last_db_wait_log = now
            else:
                if now - last_db_wait_log >= 5:
                    print(
                        "[launcher] no database target detected; check PGHOST, "
                        "PGPORT, PGUSER, PGPASSWORD, PGDATABASE",
                        flush=True,
                    )
                    last_db_wait_log = now
            restart_after[name] = now + RETRY_DELAY_SECONDS
            continue

        start_service(spec)
        restart_after[name] = 0.0
        time.sleep(1.0)

    time.sleep(1.0)
