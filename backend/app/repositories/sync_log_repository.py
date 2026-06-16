from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.conversation import SyncLog


class SyncLogRepository:
    def __init__(self, db: Session):
        self.db = db

    def list(self, provider: str | None = None, provider_account_id: UUID | None = None) -> list[SyncLog]:
        statement = select(SyncLog).order_by(SyncLog.started_at.desc())
        if provider:
            statement = statement.where(SyncLog.provider == provider)
        if provider_account_id:
            statement = statement.where(SyncLog.provider_account_id == provider_account_id)
        return list(self.db.scalars(statement))

    def get_by_id(self, sync_log_id: UUID) -> SyncLog | None:
        return self.db.get(SyncLog, sync_log_id)

    def add(self, sync_log: SyncLog) -> SyncLog:
        self.db.add(sync_log)
        return sync_log
