from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.models.conversation import ConversationNote
from app.repositories.conversation_note_repository import ConversationNoteRepository
from app.services.conversation_service import ConversationService


class ConversationNoteService:
    def __init__(self, db: Session):
        self.db = db
        self.repository = ConversationNoteRepository(db)

    def list_notes(self, conversation_id: UUID) -> list[ConversationNote]:
        ConversationService(self.db).get_conversation(conversation_id)
        return self.repository.list_by_conversation(conversation_id)

    def add_note(self, *, conversation_id: UUID, author_id: UUID, body: str) -> ConversationNote:
        ConversationService(self.db).get_conversation(conversation_id)
        normalized_body = body.strip()
        if not normalized_body:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail='Note body is required')

        note = ConversationNote(
            conversation_id=conversation_id,
            author_id=author_id,
            body=normalized_body,
        )
        self.repository.add(note)
        self.db.commit()
        self.db.refresh(note)
        return note
