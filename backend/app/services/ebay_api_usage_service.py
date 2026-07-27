from dataclasses import dataclass
from datetime import UTC, date, datetime

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models.ebay_api_usage import EbayApiUsage
from app.modules.config_management.service import ConfigService


@dataclass(frozen=True)
class EbayApiUsageSummary:
    usage_date: date
    call_count: int
    daily_limit: int

    @property
    def remaining(self) -> int:
        return max(self.daily_limit - self.call_count, 0)


class EbayApiUsageService:
    def __init__(self, db: Session):
        self.db = db
        self.settings = get_settings()

    def _daily_limit(self) -> int:
        return ConfigService(self.db).get_int('api.ebay_daily_api_limit', self.settings.ebay_daily_api_limit)

    def get_today_usage(self) -> EbayApiUsageSummary:
        usage = self._get_or_create_usage_row(self._today())
        self.db.commit()
        self.db.refresh(usage)
        return self._to_summary(usage)

    def reserve_calls(self, call_count: int) -> EbayApiUsageSummary:
        if call_count <= 0:
            return self.get_today_usage()

        usage = self._get_or_create_usage_row(self._today(), lock=True)
        next_count = usage.call_count + call_count
        remaining = max(usage.daily_limit - usage.call_count, 0)
        if next_count > usage.daily_limit:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=(
                    f'eBay daily API limit reached. '
                    f'{remaining} of {usage.daily_limit} calls remaining today.'
                ),
            )

        usage.call_count = next_count
        usage.updated_at = datetime.now(UTC)
        self.db.commit()
        self.db.refresh(usage)
        return self._to_summary(usage)

    def _get_or_create_usage_row(self, usage_date: date, *, lock: bool = False) -> EbayApiUsage:
        statement = select(EbayApiUsage).where(EbayApiUsage.usage_date == usage_date)
        if lock:
            statement = statement.with_for_update()

        usage = self.db.scalar(statement)
        if usage:
            self._sync_daily_limit(usage)
            return usage

        usage = EbayApiUsage(
            usage_date=usage_date,
            call_count=0,
            daily_limit=self._daily_limit(),
        )
        self.db.add(usage)
        try:
            self.db.commit()
            self.db.refresh(usage)
            return usage
        except IntegrityError:
            self.db.rollback()
            statement = select(EbayApiUsage).where(EbayApiUsage.usage_date == usage_date)
            if lock:
                statement = statement.with_for_update()
            existing_usage = self.db.scalar(statement)
            if existing_usage:
                self._sync_daily_limit(existing_usage)
                return existing_usage
            raise

    def _sync_daily_limit(self, usage: EbayApiUsage) -> None:
        daily_limit = self._daily_limit()
        if usage.daily_limit == daily_limit:
            return

        usage.daily_limit = daily_limit
        usage.updated_at = datetime.now(UTC)

    def _to_summary(self, usage: EbayApiUsage) -> EbayApiUsageSummary:
        return EbayApiUsageSummary(
            usage_date=usage.usage_date,
            call_count=usage.call_count,
            daily_limit=usage.daily_limit,
        )

    def _today(self) -> date:
        return datetime.now(UTC).date()
