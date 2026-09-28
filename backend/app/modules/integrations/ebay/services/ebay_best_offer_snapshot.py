"""Replace the account's visible current cache without deleting action/history records."""
from datetime import UTC, datetime
from uuid import UUID, uuid4

from sqlalchemy import select
from app.models.conversation import SyncLog, SyncLogStatus

SNAPSHOT = 'EBAY_BEST_OFFER_SNAPSHOT'


def replace_current_snapshot(db, account_id, offer_ids):
    # Callers hold the existing account operation lock. The complete set becomes
    # visible in one commit; incomplete provider scans must never call this.
    snapshot = db.scalar(select(SyncLog).where(SyncLog.sync_type == SNAPSHOT,
        SyncLog.provider_account_id == account_id).order_by(SyncLog.started_at.desc()).limit(1))
    now = datetime.now(UTC)
    if snapshot is None:
        snapshot = SyncLog(id=uuid4(), provider='EBAY', provider_account_id=account_id,
            sync_type=SNAPSHOT, status=SyncLogStatus.SUCCESS)
        db.add(snapshot)
    ids = sorted({str(value) for value in offer_ids})
    snapshot.started_at = snapshot.completed_at = now
    snapshot.status = SyncLogStatus.SUCCESS
    snapshot.records_processed = len(ids)
    snapshot.sync_metadata = {'offer_ids': ids}
    snapshot.error_message = None
    db.flush()
    return snapshot


def current_snapshot_ids(db, account_id=None):
    statement = select(SyncLog).where(SyncLog.sync_type == SNAPSHOT, SyncLog.status == SyncLogStatus.SUCCESS)
    if account_id:
        statement = statement.where(SyncLog.provider_account_id == account_id)
    ids, snapshots, accounts = set(), [], set()
    for snapshot in db.scalars(statement.order_by(SyncLog.started_at.desc())):
        if snapshot.provider_account_id in accounts:
            continue
        accounts.add(snapshot.provider_account_id)
        ids.update(UUID(value) for value in (snapshot.sync_metadata or {}).get('offer_ids', []))
        snapshots.append({'account_id': snapshot.provider_account_id, 'synced_at': snapshot.completed_at})
    return ids, snapshots
