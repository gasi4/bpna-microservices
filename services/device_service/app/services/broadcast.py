from fastapi import WebSocket


async def broadcast_bytes(clients: set[WebSocket], payload: bytes) -> None:
    dead = set()
    for client in set(clients):
        try:
            await client.send_bytes(payload)
        except Exception:
            dead.add(client)
    clients.difference_update(dead)


async def broadcast_text(clients: set[WebSocket], payload: str) -> None:
    dead = set()
    for client in set(clients):
        try:
            await client.send_text(payload)
        except Exception:
            dead.add(client)
    clients.difference_update(dead)
