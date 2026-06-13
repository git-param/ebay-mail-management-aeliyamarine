from functools import lru_cache
from pathlib import Path

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


BACKEND_DIR = Path(__file__).resolve().parents[2]
ENV_FILE = BACKEND_DIR / '.env'


class Settings(BaseSettings):
    project_name: str = 'Mail Management API'
    api_version: str = '1.0.0'

    database_url: str = Field(validation_alias='DATABASE_URL')
    secret_key: str = Field(validation_alias='SECRET_KEY')
    algorithm: str = 'HS256'

    access_token_expire_minutes: int = Field(default=15, validation_alias='ACCESS_TOKEN_EXPIRE_MINUTES')
    refresh_token_expire_days: int = Field(default=30, validation_alias='REFRESH_TOKEN_EXPIRE_DAYS')
    password_reset_token_expire_minutes: int = Field(
        default=30,
        validation_alias='PASSWORD_RESET_TOKEN_EXPIRE_MINUTES',
    )
    frontend_url: str = Field(default='http://localhost:5173', validation_alias='FRONTEND_URL')
    backend_cors_origins: str = Field(
        default='http://localhost:5173,http://127.0.0.1:5173',
        validation_alias='BACKEND_CORS_ORIGINS',
    )

    model_config = SettingsConfigDict(env_file=ENV_FILE, env_file_encoding='utf-8', extra='ignore')

    @field_validator('database_url')
    @classmethod
    def require_postgresql_url(cls, value: str) -> str:
        if not value:
            raise ValueError('DATABASE_URL must be set in backend/.env')
        if not value.startswith(('postgresql://', 'postgresql+psycopg://', 'postgresql+psycopg2://')):
            raise ValueError('DATABASE_URL must be a PostgreSQL SQLAlchemy URL')
        return value

    @property
    def cors_origins(self) -> list[str]:
        return [origin.strip() for origin in self.backend_cors_origins.split(',') if origin.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
