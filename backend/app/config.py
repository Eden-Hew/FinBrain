import re
from functools import lru_cache

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from app.schemas import UserRole


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_name: str = "FinBrain OS"
    database_url: str = "sqlite:///./finbrain.db"
    token_root_secret: str = "development-only-secret-change-me-now"
    token_hash_secret: str | None = None
    vault_master_key: str | None = None
    vault_auto_rotation_enabled: bool = False
    vault_rotation_interval_days: int = 30
    vault_rotation_check_seconds: int = 60
    vault_rotation_batch_size: int = 100
    gemini_api_key: str | None = None
    gemini_reasoning_model: str = "gemini-3.6-flash"
    gemini_embedding_model: str = "gemini-embedding-001"
    morpheus_api_key: str | None = None
    morpheus_base_url: str = "https://api.mor.org/api/v1"
    morpheus_model: str = "deepseek-v4-flash"
    enable_gliner: bool = True
    gliner_model_name: str = "urchade/gliner_multi_pii-v1"
    gliner_device: str = "cpu"
    allow_offline_demo: bool = True
    cors_origins: str = "http://localhost:5173,http://127.0.0.1:5173"
    cors_origin_regex: str | None = r"^https?://(localhost|127\.0\.0\.1):517[3-9]$"
    telegram_bot_token: str | None = None
    telegram_mode: str = "polling"
    telegram_operator_roles: str = ""
    telegram_allowed_chat_types: str = "private"
    telegram_draft_ttl_seconds: int = 600
    telegram_max_file_bytes: int = 10_000_000
    telegram_max_extracted_chars: int = 100_000
    telegram_max_pdf_pages: int = 50
    telegram_max_docx_members: int = 1_000
    telegram_max_docx_uncompressed_bytes: int = 25_000_000
    enable_ocr: bool = True
    ocr_min_text_chars: int = 40
    ocr_max_pages: int = 20
    ocr_max_image_bytes: int = 10_000_000
    telegram_delete_source_after_ingest: bool = False
    telegram_status_limit: int = 5
    telegram_heartbeat_seconds: int = 30
    telegram_preview_chars: int = 1_200
    telegram_enrichment_concurrency: int = 1
    email_connector_enabled: bool = False
    email_imap_host: str = ""
    email_imap_port: int = 993
    email_imap_username: str = ""
    email_imap_password: str = ""
    email_imap_folder: str = "INBOX"
    email_imap_use_ssl: bool = True
    email_sync_interval_seconds: int = 60
    email_max_messages_per_sync: int = 25
    email_include_attachments: bool = True
    structured_csv_max_file_bytes: int = 10_000_000
    structured_csv_max_rows: int = 500
    structured_csv_max_columns: int = 20
    structured_csv_max_cell_chars: int = 4_000
    application_timezone: str = "Asia/Kuala_Lumpur"
    service_instance_id: str | None = None
    railway_service_id: str | None = None
    supabase_url: str = ""
    supabase_jwt_issuer: str = ""
    supabase_jwt_audience: str = "authenticated"
    supabase_jwt_algorithms: str = "RS256,ES256"
    supabase_service_role_key: str | None = None
    einvoice_document_bucket: str = "einvoice-documents"
    log_level: str = "INFO"
    sentry_dsn: str | None = None
    sentry_environment: str = "development"
    sentry_traces_sample_rate: float = 0.0

    @field_validator(
        "telegram_draft_ttl_seconds",
        "telegram_max_file_bytes",
        "telegram_max_extracted_chars",
        "telegram_max_pdf_pages",
        "telegram_max_docx_members",
        "telegram_max_docx_uncompressed_bytes",
        "ocr_min_text_chars",
        "ocr_max_pages",
        "ocr_max_image_bytes",
        "telegram_status_limit",
        "telegram_heartbeat_seconds",
        "telegram_preview_chars",
        "telegram_enrichment_concurrency",
        "email_imap_port",
        "email_sync_interval_seconds",
        "email_max_messages_per_sync",
        "structured_csv_max_file_bytes",
        "structured_csv_max_rows",
        "structured_csv_max_columns",
        "structured_csv_max_cell_chars",
        "vault_rotation_interval_days",
        "vault_rotation_check_seconds",
        "vault_rotation_batch_size",
    )
    @classmethod
    def positive_connector_limits(cls, value: int) -> int:
        if value <= 0:
            raise ValueError("Connector and ingestion limits must be positive")
        return value

    @property
    def token_identity_secret(self) -> str:
        return self.token_hash_secret or self.token_root_secret

    @property
    def vault_wrapping_secret(self) -> str:
        return self.vault_master_key or self.token_root_secret

    @field_validator("telegram_mode")
    @classmethod
    def supported_telegram_mode(cls, value: str) -> str:
        if value != "polling":
            raise ValueError("Only Telegram polling mode is supported locally")
        return value

    @property
    def cors_origin_list(self) -> list[str]:
        return [item.strip() for item in self.cors_origins.split(",") if item.strip()]

    @property
    def telegram_allowed_chat_type_set(self) -> set[str]:
        return {
            item.strip() for item in self.telegram_allowed_chat_types.split(",") if item.strip()
        }

    @property
    def telegram_operator_role_map(self) -> dict[int, UserRole]:
        result: dict[int, UserRole] = {}
        for item in self.telegram_operator_roles.split(","):
            item = item.strip()
            if not item:
                continue
            try:
                user_id_text, role_text = item.split(":", 1)
                user_id = int(user_id_text)
                role = UserRole(role_text)
            except (ValueError, TypeError) as error:
                raise ValueError(
                    "TELEGRAM_OPERATOR_ROLES must contain user_id:role entries"
                ) from error
            if user_id <= 0 or user_id in result:
                raise ValueError("Telegram operator IDs must be unique positive integers")
            result[user_id] = role
        return result

    @property
    def email_configured(self) -> bool:
        return bool(
            self.email_connector_enabled
            and self.email_imap_host
            and self.email_imap_username
            and self.email_imap_password
        )

    @property
    def database_backend(self) -> str:
        return (
            "postgresql"
            if self.database_url.startswith(("postgres://", "postgresql"))
            else "sqlite"
        )

    @property
    def production_secret_configured(self) -> bool:
        secrets = (
            self.token_root_secret,
            self.token_hash_secret,
            self.vault_master_key,
        )
        return all(
            secret is not None
            and len(secret) >= 32
            and not secret.startswith(("development-only", "replace-with-"))
            for secret in secrets
        ) and len(set(secrets)) == len(secrets)

    @property
    def effective_service_instance_id(self) -> str:
        """Stable namespace separating local and deployed worker heartbeats."""
        raw = self.service_instance_id or (
            f"railway-{self.railway_service_id}" if self.railway_service_id else "local"
        )
        normalized = re.sub(r"[^a-zA-Z0-9_.-]+", "-", raw.strip()).strip("-.")
        return (normalized or "local")[:100]

    @property
    def supabase_jwks_url(self) -> str:
        return f"{self.supabase_url.rstrip('/')}/auth/v1/.well-known/jwks.json"

    @property
    def effective_supabase_jwt_issuer(self) -> str:
        return self.supabase_jwt_issuer or f"{self.supabase_url.rstrip('/')}/auth/v1"

    @property
    def supabase_jwt_algorithm_list(self) -> list[str]:
        allowed = {"RS256", "ES256"}
        algorithms = [
            item.strip() for item in self.supabase_jwt_algorithms.split(",") if item.strip()
        ]
        if not algorithms or any(item not in allowed for item in algorithms):
            raise ValueError("SUPABASE_JWT_ALGORITHMS must contain only RS256 or ES256")
        return algorithms


@lru_cache
def get_settings() -> Settings:
    return Settings()
