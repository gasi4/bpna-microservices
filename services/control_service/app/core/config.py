from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    auth_service_url: str = "http://localhost:8001"
    device_service_url: str = "http://localhost:8003"
    wifi_service_url: str = "http://localhost:8005"


settings = Settings()
