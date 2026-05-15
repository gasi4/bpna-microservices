from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    auth_service_url: str = "http://localhost:8001"
    telemetry_service_url: str = "http://localhost:8002"
    control_service_url: str = "http://localhost:8004"
    wifi_service_url: str = "http://localhost:8005"
    device_ws_url: str = "ws://localhost:8003"
    wifi_ws_url: str = "ws://localhost:8005"
    static_dir: str = "/static"


settings = Settings()
