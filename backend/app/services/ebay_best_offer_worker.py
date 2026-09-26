"""Bounded spawned batch worker; sessions and locks are child-owned."""
import multiprocessing
import os
import socket
from datetime import UTC, datetime
from uuid import UUID
from sqlalchemy import update
from fastapi import HTTPException
from app.models.conversation import SyncLog, SyncLogStatus
from app.services.ebay_best_offer_lock import account_operation_lock
from app.services.ebay_best_offer_job_service import read_config

_workers = {}


def claim(db, job_id, token):
    result = db.execute(update(SyncLog).where(SyncLog.id == job_id,
        SyncLog.status == SyncLogStatus.PENDING,
        SyncLog.sync_metadata['reservation_token'].astext == token).values(status=SyncLogStatus.RUNNING))
    db.commit()
    return result.rowcount == 1


def run_batch(batch_id, token, stop_event):
    from app.db.session import SessionLocal
    from app.modules.integrations.ebay.services.ebay_best_offer_sync_service import EbayBestOfferSyncService
    batch_id = UUID(str(batch_id))
    with SessionLocal() as batch_db:
        try:
            with account_operation_lock(batch_db.get_bind(), 'batch-execution'):
                if not claim(batch_db, batch_id, token):
                    return
                batch = batch_db.get(SyncLog, batch_id)
                metadata = dict(batch.sync_metadata)
                metadata.update(pid=os.getpid(), host=socket.gethostname(), heartbeat=datetime.now(UTC).isoformat())
                batch.sync_metadata = metadata
                batch_db.commit()
                failed = False
                for job_id in metadata['jobs']:
                    with SessionLocal() as db:
                        job_id = UUID(job_id)
                        if not claim(db, job_id, token):
                            continue
                        job = db.get(SyncLog, job_id)
                        def should_stop():
                            parent = multiprocessing.parent_process()
                            if stop_event.is_set() or (parent is not None and not parent.is_alive()):
                                return True
                            if metadata['trigger'] == 'auto':
                                with SessionLocal() as config_db:
                                    return not read_config(config_db)['enabled']
                            return False
                        try:
                            result = EbayBestOfferSyncService(db).sync_current(job.provider_account_id,
                                job_id=job.id, should_stop=should_stop)
                            job = db.get(SyncLog, job_id)
                            job.records_processed = result['offers_synced']
                            job.sync_metadata = {**job.sync_metadata, **result}
                            job.status = SyncLogStatus.SUCCESS if result['outcome'] == 'SUCCESS' else SyncLogStatus.FAILED
                            job.error_message = None if job.status == SyncLogStatus.SUCCESS else str(result.get('errors') or result['outcome'])
                        except Exception as exc:
                            db.rollback()
                            job = db.get(SyncLog, job_id)
                            job.status = SyncLogStatus.FAILED
                            job.error_message = str(getattr(exc, 'detail', None) or str(exc))[:1000]
                        job.completed_at = datetime.now(UTC)
                        failed = failed or job.status == SyncLogStatus.FAILED
                        db.commit()
                    batch_db.expire_all()
                    batch = batch_db.get(SyncLog, batch_id)
                    batch.sync_metadata = {**batch.sync_metadata, 'heartbeat': datetime.now(UTC).isoformat()}
                    batch_db.commit()
                batch.status = SyncLogStatus.FAILED if failed else SyncLogStatus.SUCCESS
                batch.completed_at = datetime.now(UTC)
                batch_db.commit()
        except HTTPException as exc:
            if exc.status_code == 409:
                return  # Duplicate dispatch must not alter a live worker's jobs.
            raise
        except Exception:
            batch_db.rollback()
            batch = batch_db.get(SyncLog, batch_id)
            if batch and batch.status in {SyncLogStatus.PENDING, SyncLogStatus.RUNNING}:
                batch.status = SyncLogStatus.FAILED
                batch.error_message = 'Best Offer worker failed before completion'
                batch.completed_at = datetime.now(UTC)
                ids = (batch.sync_metadata or {}).get('jobs', [])
                batch_db.execute(update(SyncLog).where(SyncLog.id.in_(ids), SyncLog.status.in_([SyncLogStatus.PENDING, SyncLogStatus.RUNNING])).values(status=SyncLogStatus.FAILED, completed_at=datetime.now(UTC), error_message='Batch worker failed'))
                batch_db.commit()


def dispatch(reservation):
    if not reservation.get('newly_reserved'):
        return reservation
    for key, (process, _) in list(_workers.items()):
        if not process.is_alive():
            process.join()
            process.close()
            del _workers[key]
    context = multiprocessing.get_context('spawn')
    event = context.Event()
    process = context.Process(target=run_batch, args=(str(reservation['batch_id']), reservation['reservation_token'], event), daemon=False)
    try:
        process.start()
        _workers[str(reservation['batch_id'])] = (process, event)
    except Exception:
        from app.db.session import SessionLocal
        with SessionLocal() as db:
            ids = [reservation['batch_id']] + [j['id'] for j in reservation['jobs']]
            db.execute(update(SyncLog).where(SyncLog.id.in_(ids), SyncLog.status == SyncLogStatus.PENDING)
                .values(status=SyncLogStatus.FAILED, completed_at=datetime.now(UTC), error_message='Worker spawn failed'))
            db.commit()
        raise
    return reservation


def shutdown_workers():
    for process, event in _workers.values():
        event.set()
    for batch_id, (process, _) in _workers.items():
        process.join(timeout=75)
        if process.is_alive():
            # Only this parent's read-only synchronization child is supervised.
            process.terminate()
            process.join(timeout=5)
            from app.db.session import SessionLocal
            with SessionLocal() as db:
                batch = db.get(SyncLog, UUID(batch_id))
                ids = [UUID(batch_id)] + [UUID(i) for i in (batch.sync_metadata or {}).get('jobs', [])] if batch else []
                db.execute(update(SyncLog).where(SyncLog.id.in_(ids), SyncLog.status.in_([SyncLogStatus.PENDING, SyncLogStatus.RUNNING])).values(status=SyncLogStatus.FAILED, completed_at=datetime.now(UTC), error_message='Backend shutdown interrupted synchronization'))
                db.commit()
        process.close()
    _workers.clear()
