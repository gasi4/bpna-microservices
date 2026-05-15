import asyncio
from urllib.parse import urlencode

import websockets
from fastapi import WebSocket

from app.core.config import settings


def get_upstream_ws_url(path: str, query_params: dict) -> str:
    base_ws = settings.wifi_ws_url if path == "wifi-measurements" else settings.device_ws_url
    upstream_path = "ws/measurements" if path == "wifi-measurements" else f"ws/{path}"
    query = urlencode(query_params)
    upstream_url = f"{base_ws}/{upstream_path}"
    if query:
        upstream_url = f"{upstream_url}?{query}"
    return upstream_url


async def proxy_websocket(websocket: WebSocket, path: str) -> None:
    await websocket.accept()
    upstream_url = get_upstream_ws_url(path, dict(websocket.query_params))

    async with websockets.connect(upstream_url) as upstream:
        async def client_to_upstream():
            while True:
                message = await websocket.receive()
                if message.get("text") is not None:
                    await upstream.send(message["text"])
                elif message.get("bytes") is not None:
                    await upstream.send(message["bytes"])

        async def upstream_to_client():
            async for message in upstream:
                if isinstance(message, bytes):
                    await websocket.send_bytes(message)
                else:
                    await websocket.send_text(message)

        tasks = [
            asyncio.create_task(client_to_upstream()),
            asyncio.create_task(upstream_to_client()),
        ]
        await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
        for task in tasks:
            task.cancel()
