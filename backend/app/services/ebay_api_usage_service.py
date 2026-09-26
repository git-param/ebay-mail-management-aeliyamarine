from dataclasses import dataclass
from datetime import UTC, date, datetime

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.ebay_api_usage import EbayApiUsage


@dataclass(frozen=True)
class EbayApiUsageSummary:
    usage_date: date
    api_name: str
    call_count: int
    daily_limit: int

    @property
    def remaining(self) -> int:
        return max(self.daily_limit - self.call_count, 0)


class EbayApiUsageService:
    COMMERCE = 'commerce'
    FULFILLMENT = 'fulfillment'
    BESTSELLER = 'bestseller'
    API_NAMES = (COMMERCE, FULFILLMENT, BESTSELLER)
    DEFAULT_DAILY_LIMIT = 100

    def __init__(self, db: Session):
        self.db = db

    def _daily_limit(self, api_name: str, session=None) -> int:
        # Configuration reads must never commit the caller's transaction.
        from app.models.app_config import AppConfigSetting
        value = (session or self.db).scalar(select(AppConfigSetting.value).where(
            AppConfigSetting.config_key == f'api.ebay_{api_name}_daily_limit'))
        fallback = 2500000 if api_name == self.BESTSELLER else self.DEFAULT_DAILY_LIMIT
        return max(1, int(value)) if value is not None else fallback

    def get_today_usage(self, api_name: str = COMMERCE) -> EbayApiUsageSummary:
        api_name = self._normalize_api_name(api_name)
        usage = self.db.scalar(select(EbayApiUsage).where(
            EbayApiUsage.usage_date == self._today(), EbayApiUsage.api_name == api_name))
        return EbayApiUsageSummary(self._today(), api_name, usage.call_count if usage else 0,
                                   self._daily_limit(api_name))

    def get_today_usage_all(self) -> list[EbayApiUsageSummary]:
        return [self.get_today_usage(name) for name in self.API_NAMES]

    def reserve_calls(self, call_count: int, api_name: str = COMMERCE, *, account_id=None,
                      operation=None, job_id=None, action_id=None, attempt_number=1):
        from sqlalchemy.dialects.postgresql import insert
        from sqlalchemy.orm import Session as AccountingSession
        from app.models.ebay_api_call_attempt import EbayApiCallAttempt
        from uuid import uuid4
        api_name = self._normalize_api_name(api_name)
        if call_count <= 0:
            return self.get_today_usage(api_name)
        # Independent short transaction: shared quota + attribution are atomic,
        # including concurrent first use. Never commit pending offer/message work.
        engine = getattr(self.db.get_bind(), 'engine', self.db.get_bind())
        with AccountingSession(engine) as accounting, accounting.begin():
            daily_limit = self._daily_limit(api_name, accounting)
            now = datetime.now(UTC)
            accounting.execute(insert(EbayApiUsage).values(id=uuid4(), usage_date=now.date(),
                api_name=api_name, call_count=0, daily_limit=daily_limit, created_at=now, updated_at=now)
                .on_conflict_do_nothing(index_elements=['usage_date', 'api_name']))
            usage = accounting.scalar(select(EbayApiUsage).where(
                EbayApiUsage.usage_date == now.date(), EbayApiUsage.api_name == api_name).with_for_update())
            if usage.call_count + call_count > daily_limit:
                raise HTTPException(status_code=429, detail=f'eBay {api_name} daily API limit reached')
            usage.daily_limit = daily_limit
            usage.call_count += call_count
            usage.updated_at = now
            if operation:
                for offset in range(call_count):
                    self._last_attempt_id = uuid4()
                    accounting.add(EbayApiCallAttempt(id=self._last_attempt_id, usage_id=usage.id, account_id=account_id,
                        operation=operation, job_id=job_id, action_id=action_id,
                        attempt_number=attempt_number + offset, outcome='RESERVED'))
            summary = self._to_summary(usage)
        return summary

    def reserve_attempt(self, *, account_id, operation, job_id=None, action_id=None, attempt_number=1):
        # Return the durable attempt ID to record the actual transport outcome.
        self.reserve_calls(1, self.BESTSELLER, account_id=account_id, operation=operation,
                           job_id=job_id, action_id=action_id, attempt_number=attempt_number)
        return self._last_attempt_id

    def finish_attempt(self, attempt_id, outcome):
        from sqlalchemy.orm import Session as AccountingSession
        from app.models.ebay_api_call_attempt import EbayApiCallAttempt
        with AccountingSession(getattr(self.db.get_bind(), 'engine', self.db.get_bind())) as accounting:
            attempt = accounting.get(EbayApiCallAttempt, attempt_id)
            if attempt:
                attempt.outcome = outcome
                accounting.commit()

    def attribution(self):
        from sqlalchemy import func
        from app.models.ebay_api_call_attempt import EbayApiCallAttempt
        from app.models.ebay_account import EbayAccount
        rows = self.db.execute(select(EbayApiCallAttempt.account_id, EbayAccount.account_name,
            EbayApiCallAttempt.operation, func.count()).outerjoin(EbayAccount,
            EbayAccount.id == EbayApiCallAttempt.account_id).where(
            EbayApiCallAttempt.created_at >= datetime.combine(self._today(), datetime.min.time(), tzinfo=UTC))
            .group_by(EbayApiCallAttempt.account_id, EbayAccount.account_name, EbayApiCallAttempt.operation))
        grouped = {}
        for account_id, name, operation, count in rows:
            key = str(account_id) if account_id else 'unassigned'
            item = grouped.setdefault(key, {'account_id': account_id, 'account_name': name or 'Unassigned',
                'GetBestOffers': 0, 'RespondToBestOffer': 0, 'total': 0})
            item[operation] = count
            item['total'] += count
        return list(grouped.values())

    def _to_summary(self, usage: EbayApiUsage) -> EbayApiUsageSummary:
        return EbayApiUsageSummary(
            usage_date=usage.usage_date,
            api_name=usage.api_name,
            call_count=usage.call_count,
            daily_limit=usage.daily_limit,
        )

    def _today(self) -> date:
        return datetime.now(UTC).date()

    def _normalize_api_name(self, api_name: str) -> str:
        normalized = str(api_name or self.COMMERCE).strip().lower()
        if normalized == 'best_offer':
            return self.BESTSELLER
        if normalized not in self.API_NAMES:
            return self.COMMERCE
        return normalized
