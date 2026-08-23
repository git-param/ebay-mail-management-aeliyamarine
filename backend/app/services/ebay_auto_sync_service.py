import asyncio
import logging
from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select

from app.db.session import SessionLocal
from app.models.ebay_account import EbayAccount, EbayConnectionStatus
from app.modules.config_management.service import ConfigService
from app.modules.integrations.ebay.services.ebay_sync_service import EbaySyncService
from app.services.ebay_sync_worker import spawn_ebay_sync_processes

logger = logging.getLogger(__name__)

AUTO_SYNC_ENABLED_KEY = 'api.ebay_auto_sync_enabled'
AUTO_SYNC_INTERVAL_HOURS_KEY = 'api.ebay_auto_sync_interval_hours'
AUTO_SYNC_INTERVAL_MINUTES_KEY = 'api.ebay_auto_sync_interval_minutes'
AUTO_SYNC_CHECK_SECONDS = 60
MIN_AUTO_SYNC_INTERVAL_MINUTES = 2


def get_auto_sync_interval_minutes(config: ConfigService) -> int:
    interval_minutes = config.get_int(AUTO_SYNC_INTERVAL_MINUTES_KEY, 0)
    if interval_minutes:
        return max(interval_minutes, MIN_AUTO_SYNC_INTERVAL_MINUTES)
    return max(config.get_int(AUTO_SYNC_INTERVAL_HOURS_KEY, 6) * 60, MIN_AUTO_SYNC_INTERVAL_MINUTES)


async def ebay_auto_sync_loop() -> None:
    """Check the schedule without executing the long eBay sync in FastAPI."""
    while True:
        try:
            await asyncio.to_thread(run_due_ebay_auto_sync)
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception('eBay auto sync loop failed')
        await asyncio.sleep(AUTO_SYNC_CHECK_SECONDS)


def run_due_ebay_auto_sync() -> None:
    """Queue due account syncs and hand the actual work to OS processes."""
    db = SessionLocal()
    try:
        config = ConfigService(db)
        if not config.get_bool(AUTO_SYNC_ENABLED_KEY, False):
            return

        interval_minutes = get_auto_sync_interval_minutes(config)
        latest_sync_at = db.scalar(
            select(func.max(EbayAccount.last_sync_at))
            .where(EbayAccount.connection_status == EbayConnectionStatus.CONNECTED)
            .where(EbayAccount.is_active.is_(True))
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

        connected_count = db.scalar(
            select(func.count(EbayAccount.id))
            .where(EbayAccount.connection_status == EbayConnectionStatus.CONNECTED)
            .where(EbayAccount.is_active.is_(True))
        )
        if not connected_count:
            return

        queued = EbaySyncService(db).queue_sync_all_connected_accounts(
            trigger='AUTO',
        )

        jobs = [
            (account.id, sync_log.id, None)
            for account, sync_log in queued
        ]
        if not jobs:
            return

        pids = spawn_ebay_sync_processes(jobs)
        logger.warning(
            'Queued scheduled eBay sync for %s account(s); worker_pids=%s',
            len(jobs),
            pids,
        )
    finally:
        db.close()
