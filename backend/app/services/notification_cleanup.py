import asyncio
import logging
from datetime import UTC, datetime, timedelta

from app.db.session import SessionLocal
from app.services.notification_service import NotificationService


logger = logging.getLogger(__name__)

NOTIFICATION_RETENTION = timedelta(days=1)
NOTIFICATION_CLEANUP_INTERVAL_SECONDS = 24 * 60 * 60


def clear_expired_notifications() -> int:
    cutoff = datetime.now(UTC) - NOTIFICATION_RETENTION
    db = SessionLocal()
    try:
        deleted_count = NotificationService(db).delete_older_than(cutoff)
        db.commit()
        if deleted_count:
            logger.info("Cleared %s expired notifications", deleted_count)
        return deleted_count
    except Exception:
        db.rollback()
        logger.exception("Notification cleanup failed")
        return 0
    finally:
        db.close()


async def notification_cleanup_loop() -> None:
    clear_expired_notifications()
    while True:
        await asyncio.sleep(NOTIFICATION_CLEANUP_INTERVAL_SECONDS)
        clear_expired_notifications()
