import asyncio
import logging
from app.db.session import SessionLocal
from app.services.ebay_best_offer_job_service import EbayBestOfferJobService
from app.services.ebay_best_offer_worker import dispatch, shutdown_workers

logger = logging.getLogger(__name__)


def run_due():
    with SessionLocal() as db:
        reservation = EbayBestOfferJobService(db).reserve(trigger='auto', due_only=True)
        return dispatch(reservation)


async def ebay_best_offer_auto_sync_loop():
    try:
        while True:
            try:
                check = asyncio.create_task(asyncio.to_thread(run_due))
                try:
                    await asyncio.shield(check)
                except asyncio.CancelledError:
                    # A thread cannot be cancelled. Finish reservation/dispatch
                    # before supervising every child during shutdown.
                    await check
                    raise
            except Exception:
                logger.exception('Best Offer schedule check failed')
            await asyncio.sleep(15)
    finally:
        await asyncio.to_thread(shutdown_workers)
