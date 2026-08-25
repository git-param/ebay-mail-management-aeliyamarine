from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from app.models.conversation import ConversationNote


class ConversationNoteRepository:
    def __init__(self, db: Session):
        self.db = db

    def list_by_conversation(self, conversation_id: UUID) -> list[ConversationNote]:
        statement = (
            select(ConversationNote)
            .options(joinedload(ConversationNote.author))
            .where(ConversationNote.conversation_id == conversation_id)
            .where(ConversationNote.deleted_at.is_(None))
            .order_by(ConversationNote.created_at.asc())
        )
        return list(self.db.scalars(statement))

    def get_active_for_conversation(self, *, note_id: UUID, conversation_id: UUID) -> ConversationNote | None:
        statement = (
            select(ConversationNote)
            .options(joinedload(ConversationNote.author))
            .where(ConversationNote.id == note_id)
            .where(ConversationNote.conversation_id == conversation_id)
            .where(ConversationNote.deleted_at.is_(None))
        )
        return self.db.scalar(statement)

    def add(self, note: ConversationNote) -> ConversationNote:
        self.db.add(note)
        return note
