from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_name: str = "FinBrain OS"
    database_url: str = "sqlite:///./finbrain.db"
    token_root_secret: str = "development-only-secret-change-me-now"
    gemini_api_key: str | None = None
    gemini_reasoning_model: str = "gemini-3.6-flash"
    gemini_embedding_model: str = "gemini-embedding-001"
    enable_gliner: bool = True
    allow_offline_demo: bool = True
    cors_origins: str = "http://localhost:5173"

    @property
    def cors_origin_list(self) -> list[str]:
        return [item.strip() for item in self.cors_origins.split(",") if item.strip()]

    @property
    def database_backend(self) -> str:
        return (
            "postgresql"
            if self.database_url.startswith(("postgres://", "postgresql"))
            else "sqlite"
        )

    @property
    def production_secret_configured(self) -> bool:
        return len(self.token_root_secret) >= 32 and not self.token_root_secret.startswith(
            "development-only"
        )


@lru_cache
def get_settings() -> Settings:
    return Settings()
