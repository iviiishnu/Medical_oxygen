from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # ── Database ─────────────────────────────────────────────────────────────
    db_host: str = "localhost"
    db_port: int = 5432
    db_name: str = "medical_gas_db"
    db_user: str = "postgres"
    db_password: str = "postgres"

    # ── JWT ──────────────────────────────────────────────────────────────────
    jwt_secret:                str = "change-me-in-production"
    jwt_algorithm:             str = "HS256"
    access_token_expire_hours: int = 8

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


settings = Settings()
