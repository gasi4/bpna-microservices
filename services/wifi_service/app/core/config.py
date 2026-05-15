from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    database_url: str = "postgresql+asyncpg://bpna_user:secret@localhost:5432/bpna_db"
    auth_service_url: str = "http://localhost:8001"
    device_service_url: str = "http://localhost:8003"


settings = Settings()
