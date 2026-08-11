from decimal import Decimal
from datetime import UTC, datetime
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy import select, text

from app.models.app_config import AppConfigSetting
from app.models.ebay_account import EbayAccount
from app.modules.config_management.defaults import DEFAULT_CONFIGS

HIDDEN_CONFIG_KEYS = {'api.ebay_daily_api_limit', 'api.ebay_auto_sync_enabled'}


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
        return list(self.db.scalars(
            select(AppConfigSetting)
            .where(AppConfigSetting.section != 'pms')
            .where(AppConfigSetting.config_key.not_in(HIDDEN_CONFIG_KEYS))
            .order_by(AppConfigSetting.section, AppConfigSetting.label)
        ))

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

    def get_bool(self, key: str, default: bool = False) -> bool:
        self.ensure_defaults()
        setting = self.db.scalar(select(AppConfigSetting).where(AppConfigSetting.config_key == key))
        if not setting:
            return default
        return str(setting.value).strip().lower() in {'1', 'true', 'yes', 'on'}

    def set_value(self, key: str, value: str, user=None) -> AppConfigSetting:
        self.ensure_defaults()
        setting = self.db.scalar(select(AppConfigSetting).where(AppConfigSetting.config_key == key))
        if not setting:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='Configuration setting not found.')
        setting.value = str(value)
        setting.updated_by_user_id = getattr(user, 'id', None)
        self.db.commit()
        self.db.refresh(setting)
        return setting

    def list_account_sync_states(self) -> list[EbayAccount]:
        return list(self.db.scalars(select(EbayAccount).order_by(EbayAccount.account_name.asc())))

    def update_account_sync_cursor(self, *, account_id: UUID | None, last_sync_at: datetime | None, apply_to_all: bool) -> dict:
        statement = select(EbayAccount)
        if not apply_to_all:
            if not account_id:
                raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail='Select an eBay account or choose all accounts.')
            statement = statement.where(EbayAccount.id == account_id)
        accounts = list(self.db.scalars(statement))
        if not accounts:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='No matching eBay accounts found.')

        normalized = last_sync_at.astimezone(UTC) if last_sync_at else None
        for account in accounts:
            account.last_sync_at = normalized
            account.last_order_sync_at = normalized
            account.sync_status = 'MANUALLY_UPDATED'
        self.db.commit()
        return {'updated_count': len(accounts), 'last_sync_at': normalized}

    def delete_conversation_data(self) -> dict:
        tables = [
            'audit_logs',
            'conversation_category_history',
            'conversation_assignments',
            'notifications',
            'offer_management_entry_history',
            'offer_management_entries',
            'conversation_product_contexts',
            'conversation_notes',
            'conversation_order_contexts',
            'conversation_message_classifications',
            'conversation_sla_history',
            'conversation_status_history',
            'conversation_participants',
            'offers',
            'returns',
            'cancellations',
            'order_line_items',
            'message_attachments',
            'messages',
            'conversations',
            'orders',
        ]
        deleted = {}
        try:
            for table in tables:
                result = self.db.execute(text(f'DELETE FROM {table}'))
                deleted[table] = int(result.rowcount or 0)
            self.db.commit()
            return {'deleted': deleted, 'total_deleted': sum(deleted.values())}
        except Exception as exc:
            self.db.rollback()
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f'Conversation cleanup failed: {exc}') from exc

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
        if setting.value_type == 'boolean':
            return 'true' if text.lower() in {'1', 'true', 'yes', 'on'} else 'false'
        return text
