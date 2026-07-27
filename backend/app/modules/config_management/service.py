from decimal import Decimal

from fastapi import HTTPException, status
from sqlalchemy import select

from app.models.app_config import AppConfigSetting
from app.modules.config_management.defaults import DEFAULT_CONFIGS


class ConfigService:
    def __init__(self, db):
        self.db = db

    def ensure_defaults(self) -> None:
        for item in DEFAULT_CONFIGS:
            exists = self.db.scalar(select(AppConfigSetting).where(AppConfigSetting.config_key == item['config_key']))
            if not exists:
                self.db.add(AppConfigSetting(**item))
        self.db.commit()

    def list_settings(self) -> list[AppConfigSetting]:
        self.ensure_defaults()
        return list(self.db.scalars(select(AppConfigSetting).order_by(AppConfigSetting.section, AppConfigSetting.label)))

    def update_settings(self, settings: list[dict], user) -> list[AppConfigSetting]:
        self.ensure_defaults()
        by_key = {setting.config_key: setting for setting in self.list_settings()}
        for item in settings:
            setting = by_key.get(item.get('config_key'))
            if not setting or not setting.is_editable:
                continue
            value = self._validate_value(setting, item.get('value'))
            setting.value = value
            setting.updated_by_user_id = user.id
        self.db.commit()
        return self.list_settings()

    def get_decimal(self, key: str, default: Decimal) -> Decimal:
        self.ensure_defaults()
        setting = self.db.scalar(select(AppConfigSetting).where(AppConfigSetting.config_key == key))
        if not setting:
            return default
        try:
            return Decimal(str(setting.value))
        except Exception:
            return default

    def get_int(self, key: str, default: int) -> int:
        self.ensure_defaults()
        setting = self.db.scalar(select(AppConfigSetting).where(AppConfigSetting.config_key == key))
        if not setting:
            return default
        try:
            return int(setting.value)
        except Exception:
            return default

    def _validate_value(self, setting: AppConfigSetting, value) -> str:
        text = str(value if value is not None else '').strip()
        if not text:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=f'{setting.label} is required.')
        if setting.value_type == 'integer':
            parsed = int(text)
            if parsed < 1:
                raise ValueError
            return str(parsed)
        if setting.value_type == 'decimal':
            parsed = Decimal(text)
            if parsed < 0:
                raise ValueError
            return str(parsed)
        return text
