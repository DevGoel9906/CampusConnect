from pydantic_settings import BaseSettings
from functools import lru_cache


class Settings(BaseSettings):
    database_url: str = "postgresql+asyncpg://campusconnect:password@localhost:5432/campusconnect"
    jwt_secret: str = "local-only-jwt-secret-not-for-production-at-least-32-chars"
    jwt_refresh_secret: str = "local-only-refresh-secret-not-for-production-32-chars"
    jwt_access_expires_minutes: int = 15
    jwt_refresh_expires_days: int = 7
    cors_origins: str = "http://localhost:3000"
    api_port: int = 3001
    node_env: str = "development"

    @property
    def cors_origins_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    class Config:
        env_file = "../.env"
        extra = "ignore"


@lru_cache
def get_settings() -> Settings:
    return Settings()
