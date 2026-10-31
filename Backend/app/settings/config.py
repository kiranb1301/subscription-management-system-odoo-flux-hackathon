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

    FRONTEND_URL: str = "http://localhost:4200"
    PASSWORD_RESET_EXPIRE_MINUTES: int = 30
    EMAIL_VERIFY_EXPIRE_HOURS: int = 24

    # Leave SMTP_HOST empty to print emails to the console instead of sending them
    SMTP_HOST: str = ""
    SMTP_PORT: int = 587
    SMTP_USER: str = ""
    SMTP_PASSWORD: str = ""
    SMTP_FROM: str = "no-reply@brightloop.local"
    SMTP_USE_TLS: bool = True

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


settings = Settings()