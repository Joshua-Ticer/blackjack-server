"""Application settings, loaded from environment / .env (12-factor config)."""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_env: str = "development"
    secret_key: str = "changeme"

    database_url: str = "postgresql+asyncpg://blackjack:blackjack@localhost:5432/blackjack"
    redis_url: str = "redis://localhost:6379/0"

    jwt_algorithm: str = "HS256"
    jwt_expire_minutes: int = 60


settings = Settings()

