from functools import lru_cache
from pathlib import Path

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


BACKEND_DIR = Path(__file__).resolve().parents[2]
ENV_FILE = BACKEND_DIR / '.env'


class Settings(BaseSettings):
    project_name: str = 'ACES API'
    api_version: str = '1.0.0'

    database_url: str = Field(validation_alias='DATABASE_URL')
    secret_key: str = Field(validation_alias='SECRET_KEY')
    algorithm: str = 'HS256'

    access_token_expire_minutes: int = Field(default=15, validation_alias='ACCESS_TOKEN_EXPIRE_MINUTES')
    refresh_token_expire_days: int = Field(default=30, validation_alias='REFRESH_TOKEN_EXPIRE_DAYS')
    auth_cookie_secure: bool = Field(default=False, validation_alias='AUTH_COOKIE_SECURE')
    auth_cookie_samesite: str = Field(default='lax', validation_alias='AUTH_COOKIE_SAMESITE')
    password_reset_token_expire_minutes: int = Field(
        default=30,
        validation_alias='PASSWORD_RESET_TOKEN_EXPIRE_MINUTES',
    )
    frontend_url: str = Field(default='http://localhost:5173', validation_alias='FRONTEND_URL')
    public_backend_url: str = Field(default='', validation_alias='PUBLIC_BACKEND_URL')
    backend_cors_origins: str = Field(
        default='http://localhost:5173,http://127.0.0.1:5173',
        validation_alias='BACKEND_CORS_ORIGINS',
    )
    smtp_host: str = Field(default='', validation_alias='SMTP_HOST')
    smtp_port: int = Field(default=587, validation_alias='SMTP_PORT')
    smtp_username: str = Field(default='', validation_alias='SMTP_USERNAME')
    smtp_password: str = Field(default='', validation_alias='SMTP_PASSWORD')
    smtp_from_email: str = Field(default='', validation_alias='SMTP_FROM_EMAIL')
    smtp_use_tls: bool = Field(default=True, validation_alias='SMTP_USE_TLS')
    ebay_client_id: str = Field(default='', validation_alias='EBAY_CLIENT_ID')
    ebay_client_secret: str = Field(default='', validation_alias='EBAY_CLIENT_SECRET')
    ebay_redirect_uri: str = Field(default='', validation_alias='EBAY_REDIRECT_URI')
    ebay_runame: str = Field(default='', validation_alias='EBAY_RUNAME')
    ebay_environment: str = Field(default='SANDBOX', validation_alias='EBAY_ENVIRONMENT')
    ebay_marketplace_id: str = Field(default='EBAY_US', validation_alias='EBAY_MARKETPLACE_ID')
    ebay_browse_max_retries: int = Field(default=3, ge=1, le=10, validation_alias='EBAY_BROWSE_MAX_RETRIES')
    ebay_browse_retry_base_seconds: float = Field(
        default=0.5,
        ge=0,
        le=60,
        validation_alias='EBAY_BROWSE_RETRY_BASE_SECONDS',
    )

    ebay_daily_api_limit: int = Field(
        default=100,
        validation_alias='EBAY_DAILY_API_LIMIT',
    )
    reply_attachment_max_bytes: int = Field(default=5 * 1024 * 1024, validation_alias='REPLY_ATTACHMENT_MAX_BYTES')
    reply_attachment_upload_dir: str = Field(default='uploads/reply_attachments', validation_alias='REPLY_ATTACHMENT_UPLOAD_DIR')
    translation_api_url: str = Field(default='', validation_alias='TRANSLATION_API_URL')
    translation_api_key: str = Field(default='', validation_alias='TRANSLATION_API_KEY')
    zoho_client_id: str = Field(default='', validation_alias='ZOHO_CLIENT_ID')
    zoho_client_secret: str = Field(default='', validation_alias='ZOHO_CLIENT_SECRET')
    zoho_organization_id: str = Field(default='', validation_alias='ZOHO_ORGANIZATION_ID')
    zoho_token_file: str = Field(default='zoho_tokens.json', validation_alias='ZOHO_TOKEN_FILE')

    model_config = SettingsConfigDict(env_file=ENV_FILE, env_file_encoding='utf-8', extra='ignore')

    @field_validator('database_url')
    @classmethod
    def require_postgresql_url(cls, value: str) -> str:
        if not value:
            raise ValueError('DATABASE_URL must be set in backend/.env')
        if not value.startswith(('postgresql://', 'postgresql+psycopg://', 'postgresql+psycopg2://')):
            raise ValueError('DATABASE_URL must be a PostgreSQL SQLAlchemy URL')
        return value

    @field_validator('ebay_environment')
    @classmethod
    def validate_ebay_environment(cls, value: str) -> str:
        normalized_value = value.strip().upper()
        if normalized_value not in {'SANDBOX', 'PRODUCTION'}:
            raise ValueError('EBAY_ENVIRONMENT must be SANDBOX or PRODUCTION')
        return normalized_value

    @field_validator('ebay_daily_api_limit')
    @classmethod
    def validate_ebay_daily_api_limit(cls, value: int) -> int:
        if value < 1:
            raise ValueError('EBAY_DAILY_API_LIMIT must be at least 1')
        return value

    @field_validator('auth_cookie_samesite')
    @classmethod
    def validate_auth_cookie_samesite(cls, value: str) -> str:
        normalized_value = value.strip().lower()
        if normalized_value not in {'lax', 'strict', 'none'}:
            raise ValueError('AUTH_COOKIE_SAMESITE must be lax, strict, or none')
        return normalized_value

    @property
    def cors_origins(self) -> list[str]:
        return [origin.strip() for origin in self.backend_cors_origins.split(',') if origin.strip()]

    @property
    def reply_attachment_public_base_url(self) -> str:
        """Return the public HTTPS backend origin used for eBay media URLs."""
        return self.public_backend_url.rstrip('/')


@lru_cache
def get_settings() -> Settings:
    return Settings()
