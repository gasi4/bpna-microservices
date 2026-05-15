import asyncio
import websockets
import json
import httpx

SERVER = "http://localhost:8000"
LOGIN = "operator"
PASSWORD = "operator123"

async def fake_operator():
    # Шаг 1 — получаем токен
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            f"{SERVER}/api/auth/login",
            json={"username": LOGIN, "password": PASSWORD},  # ← json= вместо data=
        )
        print(f"Статус: {resp.status_code}")
        print(f"Ответ: {resp.json()}")
        token = resp.json()["access_token"]

    # Шаг 2 — подключаемся к WebSocket
    async with websockets.connect(
        f"ws://localhost:8000/api/telemetry/ws/operator?token={token}"
    ) as ws:
        print("Оператор подключён")
        async for message in ws:
            data = json.loads(message)
            print(f"📊 battery={data.get('battery')}% connected={data.get('connected')}")

asyncio.run(fake_operator())