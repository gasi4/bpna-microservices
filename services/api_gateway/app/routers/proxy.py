from fastapi import APIRouter, Request, Response, WebSocket

from app.core.routes import SERVICE_ROUTES
from app.services.http_proxy import proxy_http
from app.services.ws_proxy import proxy_websocket


router = APIRouter()


@router.api_route(
    "/api/{service}/{path:path}",
    methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
)
async def api_proxy(service: str, path: str, request: Request):
    base_url = SERVICE_ROUTES.get(service)
    if base_url is None:
        return Response(status_code=404, content=b"Unknown service")
    return await proxy_http(request, base_url, path)


@router.websocket("/ws/{path:path}")
async def websocket_proxy(websocket: WebSocket, path: str):
    await proxy_websocket(websocket, path)
