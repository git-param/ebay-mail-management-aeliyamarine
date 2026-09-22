from decimal import Decimal
from datetime import UTC, date, datetime, time, timedelta
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy import select, text

from app.models.app_config import AppConfigSetting
from app.models.ebay_account import EbayAccount
from app.modules.config_management.defaults import DEFAULT_CONFIGS

HIDDEN_CONFIG_KEYS = {
    'api.ebay_daily_api_limit',
    'api.ebay_auto_sync_enabled',
    'api.ebay_auto_sync_interval_hours',
}


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

    def delete_conversation_data(self, date_from: date | None, date_to: date | None) -> dict:
        start = datetime.combine(date_from, time.min, tzinfo=UTC) if date_from else None
        end = datetime.combine(date_to + timedelta(days=1), time.min, tzinfo=UTC) if date_to else None
        tables = [
            ('offer_management_entry_history', 'offer_entry_id IN (SELECT id FROM cleanup_offer_entries)'),
            ('offer_management_entries', 'id IN (SELECT id FROM cleanup_offer_entries)'),
            ('message_attachments', 'message_id IN (SELECT id FROM cleanup_messages)'),
            ('conversation_message_classifications', 'conversation_id IN (SELECT id FROM cleanup_conversations) OR conversation_message_id IN (SELECT id FROM cleanup_messages)'),
            ('offers', 'id IN (SELECT id FROM cleanup_offers)'),
            ('messages', 'id IN (SELECT id FROM cleanup_messages)'),
            ('conversation_category_history', 'conversation_id IN (SELECT id FROM cleanup_conversations)'),
            ('conversation_assignments', 'conversation_id IN (SELECT id FROM cleanup_conversations)'),
            ('conversation_product_contexts', 'conversation_id IN (SELECT id FROM cleanup_conversations)'),
            ('conversation_notes', 'conversation_id IN (SELECT id FROM cleanup_conversations)'),
            ('conversation_order_contexts', 'conversation_id IN (SELECT id FROM cleanup_conversations)'),
            ('conversation_sla_history', 'conversation_id IN (SELECT id FROM cleanup_conversations)'),
            ('conversation_status_history', 'conversation_id IN (SELECT id FROM cleanup_conversations)'),
            ('conversation_participants', 'conversation_id IN (SELECT id FROM cleanup_conversations)'),
            ('conversations', 'id IN (SELECT id FROM cleanup_conversations)'),
        ]
        deleted = {}
        try:
            conditions = []
            parameters = {}
            if start:
                conditions.append('created_at >= :start')
                parameters['start'] = start
            if end:
                conditions.append('created_at < :end')
                parameters['end'] = end
            self.db.execute(text('CREATE TEMP TABLE cleanup_conversations ON COMMIT DROP AS SELECT id FROM conversations WHERE ' + ' AND '.join(conditions)), parameters)
            self.db.execute(text('CREATE TEMP TABLE cleanup_messages ON COMMIT DROP AS SELECT id FROM messages WHERE conversation_id IN (SELECT id FROM cleanup_conversations)'))
            self.db.execute(text('CREATE TEMP TABLE cleanup_offers ON COMMIT DROP AS SELECT id FROM offers WHERE conversation_id IN (SELECT id FROM cleanup_conversations) OR message_id IN (SELECT id FROM cleanup_messages)'))
            self.db.execute(text('CREATE TEMP TABLE cleanup_offer_entries ON COMMIT DROP AS SELECT id FROM offer_management_entries WHERE related_conversation_id IN (SELECT id FROM cleanup_conversations) OR related_offer_id IN (SELECT id FROM cleanup_offers)'))
            for table, condition in tables:
                result = self.db.execute(text(f'DELETE FROM {table} WHERE {condition}'))
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
