from datetime import UTC, datetime
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.models.conversation import SyncLog, SyncLogStatus
from app.repositories.sync_log_repository import SyncLogRepository


class SyncLogService:
    def __init__(self, db: Session):
        self.db = db
        self.repository = SyncLogRepository(db)

    def list_sync_logs(self, provider: str | None = None, provider_account_id: UUID | None = None) -> list[SyncLog]:
        return self.repository.list(provider=provider, provider_account_id=provider_account_id)

    def start_sync(
        self,
        *,
        provider: str,
        sync_type: str,
        provider_account_id: UUID | None = None,
        sync_metadata: dict | None = None,
    ) -> SyncLog:
        sync_log = SyncLog(
            provider=provider,
            provider_account_id=provider_account_id,
            sync_type=sync_type,
            status=SyncLogStatus.RUNNING,
            records_processed=0,
            sync_metadata=sync_metadata,
        )
        self.repository.add(sync_log)
        self.db.commit()
        self.db.refresh(sync_log)
        return sync_log

    def complete_sync(self, sync_log_id: UUID, records_processed: int) -> SyncLog:
        sync_log = self.repository.get_by_id(sync_log_id)
        if not sync_log:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='Sync log not found')

        sync_log.status = SyncLogStatus.SUCCESS
        sync_log.completed_at = datetime.now(UTC)
        sync_log.records_processed = records_processed
        self.db.commit()
        self.db.refresh(sync_log)
        return sync_log

    def update_progress(
        self,
        sync_log_id: UUID,
        *,
        records_processed: int,
        sync_metadata: dict | None = None,
    ) -> SyncLog:
        sync_log = self.repository.get_by_id(sync_log_id)
        if not sync_log:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='Sync log not found')

        sync_log.records_processed = records_processed
        if sync_metadata:
            sync_log.sync_metadata = {
                **(sync_log.sync_metadata or {}),
                **sync_metadata,
            }
        self.db.commit()
        self.db.refresh(sync_log)
        return sync_log

    def fail_sync(self, sync_log_id: UUID, error_message: str) -> SyncLog:
        sync_log = self.repository.get_by_id(sync_log_id)
        if not sync_log:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='Sync log not found')

        sync_log.status = SyncLogStatus.FAILED
        sync_log.completed_at = datetime.now(UTC)
        sync_log.error_message = error_message
        self.db.commit()
        self.db.refresh(sync_log)
        return sync_log
