from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    APP_NAME: str = "Brightloop"
    APP_TITLE: str = "Brightloop Subscription Management API"
    APP_VERSION: str = "1.0.0"
    APP_DESCRIPTION: str = "Subscription and recurring billing platform"
    API_V1_PREFIX: str = "/api/v1"
    CORS_ORIGINS: list[str] = ["http://localhost:4200"]

    DATABASE_URL: str = "sqlite:///./brightloop.db"

    SECRET_KEY: str = "change-me-in-env"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30

    REDIS_URL: str = "redis://localhost:6379/0"

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


settings = Settings()