from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    device_secret: str = "change-me-device"
    auth_service_url: str = "http://localhost:8001"
    telemetry_service_url: str = "http://localhost:8002"
    wifi_service_url: str = "http://localhost:8005"
    detection_service_url: str = "http://localhost:8006"


settings = Settings()
