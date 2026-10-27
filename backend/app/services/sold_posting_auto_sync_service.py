import asyncio
import logging
from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select

from app.db.session import SessionLocal
from app.models.ebay_account import EbayAccount
from app.modules.config_management.service import ConfigService
from app.modules.sold_posting.models import SoldPostingSyncState
from app.modules.sold_posting.service import SoldPostingService

logger = logging.getLogger(__name__)

AUTO_SYNC_INTERVAL_MINUTES_KEY = 'sold_posting.auto_sync_interval_minutes'
AUTO_SYNC_CHECK_SECONDS = 600


async def sold_posting_auto_sync_loop() -> None:
    while True:
        try:
            await asyncio.to_thread(run_due_sold_posting_auto_sync)
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception('Sold Posting auto sync loop failed')
        await asyncio.sleep(AUTO_SYNC_CHECK_SECONDS)


def run_due_sold_posting_auto_sync() -> None:
    db = SessionLocal()
    try:
        config = ConfigService(db)
        interval_minutes = config.get_int(AUTO_SYNC_INTERVAL_MINUTES_KEY, 60)
        if interval_minutes < 1:
            return

        active_accounts = select(EbayAccount.id).where(
            EbayAccount.is_active.is_(True),
            EbayAccount.access_token.isnot(None),
        )
        latest_sync_at = db.scalar(
            select(func.max(SoldPostingSyncState.last_successful_sync_at))
            .where(SoldPostingSyncState.ebay_account_id.in_(active_accounts))
        )
        now = datetime.now(UTC)
        if latest_sync_at:
            latest_sync_at = (
                latest_sync_at.astimezone(UTC)
                if latest_sync_at.tzinfo
                else latest_sync_at.replace(tzinfo=UTC)
            )
            if latest_sync_at + timedelta(minutes=interval_minutes) > now:
                return

        if not db.scalar(select(active_accounts.exists())):
            return

        result = SoldPostingService(db).sync_all_accounts()
        logger.info(
            'Completed scheduled Sold Posting sync: accounts=%s',
            len(result.get('results', [])),
        )
    finally:
        db.close()
