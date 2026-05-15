import httpx
from fastapi import Request, Response


async def proxy_http(request: Request, base_url: str, path: str) -> Response:
    body = await request.body()
    headers = {
        key: value
        for key, value in request.headers.items()
        if key.lower() not in {"host", "content-length"}
    }

    target = f"{base_url}/{path}"
    if request.url.query:
        target = f"{target}?{request.url.query}"

    async with httpx.AsyncClient(timeout=30) as client:
        upstream = await client.request(
            request.method,
            target,
            headers=headers,
            content=body,
        )

    excluded = {"content-encoding", "transfer-encoding", "connection"}
    response_headers = {
        key: value
        for key, value in upstream.headers.items()
        if key.lower() not in excluded
    }
    return Response(
        content=upstream.content,
        status_code=upstream.status_code,
        headers=response_headers,
        media_type=upstream.headers.get("content-type"),
    )
