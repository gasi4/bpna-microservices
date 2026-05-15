import os
import signal
import subprocess
import sys
import time
from pathlib import Path
from urllib.parse import quote_plus

ROOT = Path('/opt/bpna')
SERVICES_DIR = ROOT / 'services'


def normalize_database_url(url: str | None) -> str | None:
    if not url:
        return url
    url = url.strip().strip('"').strip("'")
    if url.startswith('postgresql+asyncpg://'):
        return url
    if url.startswith('postgres://'):
        return 'postgresql+asyncpg://' + url[len('postgres://'):]
    if url.startswith('postgresql://'):
        return 'postgresql+asyncpg://' + url[len('postgresql://'):]
    return url


def derive_database_url(env: dict[str, str]) -> str | None:
    database_url = normalize_database_url(env.get('DATABASE_URL'))
    if database_url and '${{' not in database_url and '}}' not in database_url:
        return database_url

    pg_host = env.get('PGHOST')
    pg_port = env.get('PGPORT', '5432')
    pg_user = env.get('PGUSER')
    pg_password = env.get('PGPASSWORD')
    pg_database = env.get('PGDATABASE')

    if all([pg_host, pg_user, pg_password, pg_database]):
        return (
            'postgresql+asyncpg://'
            f'{quote_plus(pg_user)}:{quote_plus(pg_password)}'
            f'@{pg_host}:{pg_port}/{quote_plus(pg_database)}'
        )

    return database_url


def build_env(port: int, public: bool = False) -> dict[str, str]:
    env = os.environ.copy()
    env['PORT'] = str(port)
    env['HOSTNAME'] = '0.0.0.0' if public else '127.0.0.1'
    database_url = derive_database_url(env)
    if database_url:
        env['DATABASE_URL'] = database_url
    model_path = ROOT / 'yolo11s.pt'
    if model_path.exists():
        env['YOLO_MODEL_PATH'] = str(model_path)
    return env


SERVICE_SPECS = [
    ('auth-service', SERVICES_DIR / 'auth_service', 8001, False),
    ('telemetry-service', SERVICES_DIR / 'telemetry_service', 8002, False),
    ('device-service', SERVICES_DIR / 'device_service', 8003, False),
    ('control-service', SERVICES_DIR / 'control_service', 8004, False),
    ('wifi-service', SERVICES_DIR / 'wifi_service', 8005, False),
    ('detection-service', SERVICES_DIR / 'detection_service', 8006, False),
    ('api-gateway', SERVICES_DIR / 'api_gateway', int(os.getenv('PORT', '8000')), True),
]


processes: list[tuple[str, subprocess.Popen[str]]] = []
shutting_down = False


def terminate_all() -> None:
    global shutting_down
    if shutting_down:
        return
    shutting_down = True
    for name, process in reversed(processes):
        if process.poll() is None:
            print(f'[launcher] stopping {name}...', flush=True)
            process.terminate()
    deadline = time.time() + 10
    for name, process in reversed(processes):
        while process.poll() is None and time.time() < deadline:
            time.sleep(0.2)
        if process.poll() is None:
            print(f'[launcher] killing {name}...', flush=True)
            process.kill()


def handle_signal(signum, frame):
    print(f'[launcher] received signal {signum}, shutting down', flush=True)
    terminate_all()
    sys.exit(0)


signal.signal(signal.SIGINT, handle_signal)
signal.signal(signal.SIGTERM, handle_signal)

for name, cwd, port, public in SERVICE_SPECS:
    command = [sys.executable, '-m', 'uvicorn', 'app.main:app', '--host', '0.0.0.0' if public else '127.0.0.1', '--port', str(port)]
    print(f'[launcher] starting {name} on port {port}', flush=True)
    process = subprocess.Popen(command, cwd=str(cwd), env=build_env(port, public))
    processes.append((name, process))
    time.sleep(1.0)

exit_code = 0
while processes:
    for name, process in processes:
        code = process.poll()
        if code is not None:
            print(f'[launcher] {name} exited with code {code}', flush=True)
            exit_code = code or 0
            terminate_all()
            sys.exit(exit_code)
    time.sleep(1.0)
