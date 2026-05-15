from app.core.config import settings


SERVICE_ROUTES = {
    "auth": settings.auth_service_url,
    "telemetry": settings.telemetry_service_url,
    "session": settings.telemetry_service_url,
    "device": settings.control_service_url,
    "wifi": settings.wifi_service_url,
}
