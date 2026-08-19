"""Process-isolated eBay sync execution.

The API process only creates/claims a SyncLog and starts a child process.
The child creates its own SQLAlchemy SessionLocal connection and performs the
existing EbaySyncService workflow. This keeps a 100-180 second eBay sync from
occupying the FastAPI request/worker thread.
"""

import logging
import multiprocessing
from uuid import UUID

logger = logging.getLogger(__name__)

_processes: set[multiprocessing.Process] = set()


def _cleanup_finished_processes() -> None:
    finished = {process for process in _processes if not process.is_alive()}
    for process in finished:
        try:
            process.close()
        except ValueError:
            pass
        _processes.discard(process)


def _run_sync_process(account_id: str, sync_log_id: str, max_conversations: int | None) -> None:
    """Entry point executed inside a fresh OS process."""
    from app.db.session import SessionLocal
    from app.models.conversation import SyncLog, SyncLogStatus
    from app.models.ebay_account import EbayAccount
    from app.services.sync_log_service import SyncLogService
    from app.modules.integrations.ebay.services.ebay_sync_service import EbaySyncService

    db = SessionLocal()
    try:
        EbaySyncService(db).sync_account(
            UUID(account_id),
            max_conversations=max_conversations,
            sync_log_id=UUID(sync_log_id),
        )
    except Exception as exc:
        logger.exception(
            'Process-isolated eBay sync failed before normal finalization account_id=%s sync_log_id=%s',
            account_id,
            sync_log_id,
        )
        try:
            db.rollback()
            sync_log = db.get(SyncLog, UUID(sync_log_id))
            if sync_log and sync_log.status == SyncLogStatus.RUNNING:
                SyncLogService(db).fail_sync(UUID(sync_log_id), str(exc))

            account = db.get(EbayAccount, UUID(account_id))
            if account:
                account.sync_status = 'FAILED'
                db.commit()
        except Exception:
            db.rollback()
            logger.exception(
                'Could not persist process-level eBay sync failure account_id=%s sync_log_id=%s',
                account_id,
                sync_log_id,
            )
    finally:
        db.close()


def spawn_ebay_sync_process(
    *,
    account_id: UUID,
    sync_log_id: UUID,
    max_conversations: int | None = None,
) -> int:
    """Start one independent OS process and return its PID."""
    _cleanup_finished_processes()

    context = multiprocessing.get_context('spawn')
    process = context.Process(
        target=_run_sync_process,
        args=(str(account_id), str(sync_log_id), max_conversations),
        name=f'ebay-sync-{account_id}',
        daemon=False,
    )
    process.start()
    _processes.add(process)

    logger.warning(
        'Started process-isolated eBay sync account_id=%s sync_log_id=%s pid=%s',
        account_id,
        sync_log_id,
        process.pid,
    )
    return int(process.pid or 0)


def spawn_ebay_sync_processes(
    jobs: list[tuple[UUID, UUID, int | None]],
) -> list[int]:
    """Start multiple independent account sync processes."""
    return [
        spawn_ebay_sync_process(
            account_id=account_id,
            sync_log_id=sync_log_id,
            max_conversations=max_conversations,
        )
        for account_id, sync_log_id, max_conversations in jobs
    ]
