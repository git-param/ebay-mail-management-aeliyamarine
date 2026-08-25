from uuid import UUID
from datetime import UTC, datetime

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.models.conversation import ConversationNote
from app.repositories.conversation_note_repository import ConversationNoteRepository
from app.services.audit_service import AuditService
from app.services.conversation_service import ConversationService


class ConversationNoteService:
    def __init__(self, db: Session):
        self.db = db
        self.repository = ConversationNoteRepository(db)

    def list_notes(self, conversation_id: UUID) -> list[ConversationNote]:
        ConversationService(self.db).get_conversation(conversation_id)
        return self.repository.list_by_conversation(conversation_id)

    def add_note(self, *, conversation_id: UUID, author_id: UUID, body: str) -> ConversationNote:
        conversation = ConversationService(self.db).get_conversation(conversation_id)
        normalized_body = body.strip()
        if not normalized_body:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail='Note body is required')

        note = ConversationNote(
            conversation_id=conversation_id,
            author_id=author_id,
            body=normalized_body,
        )
        self.repository.add(note)
        self.db.flush()
        AuditService(self.db).log(
            action='INTERNAL_NOTE_CREATED',
            user_id=author_id,
            entity_type='INTERNAL_NOTE',
            entity_id=note.id,
            category='MESSAGE_MANAGEMENT',
            metadata={
                'conversation_id': str(conversation.id),
                'provider_account_id': str(conversation.provider_account_id) if conversation.provider_account_id else None,
                'note_id': str(note.id),
            },
        )
        self.db.commit()
        self.db.refresh(note)
        return note

    def update_note(self, *, conversation_id: UUID, note_id: UUID, editor_id: UUID, body: str) -> ConversationNote:
        conversation = ConversationService(self.db).get_conversation(conversation_id)
        normalized_body = body.strip()
        if not normalized_body:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail='Note body is required')

        note = self.repository.get_active_for_conversation(note_id=note_id, conversation_id=conversation_id)
        if not note:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='Internal note not found')

        previous_body = note.body
        note.body = normalized_body
        note.updated_at = datetime.now(UTC)
        self.db.flush()
        AuditService(self.db).log(
            action='INTERNAL_NOTE_UPDATED',
            user_id=editor_id,
            entity_type='INTERNAL_NOTE',
            entity_id=note.id,
            category='MESSAGE_MANAGEMENT',
            metadata={
                'conversation_id': str(conversation.id),
                'provider_account_id': str(conversation.provider_account_id) if conversation.provider_account_id else None,
                'note_id': str(note.id),
                'old': {'body': previous_body},
                'new': {'body': note.body},
            },
        )
        self.db.commit()
        self.db.refresh(note)
        return note

    def delete_note(self, *, conversation_id: UUID, note_id: UUID, deleted_by: UUID) -> None:
        conversation = ConversationService(self.db).get_conversation(conversation_id)
        note = self.repository.get_active_for_conversation(note_id=note_id, conversation_id=conversation_id)
        if not note:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='Internal note not found')

        note.deleted_at = datetime.now(UTC)
        note.deleted_by = deleted_by
        self.db.flush()
        AuditService(self.db).log(
            action='INTERNAL_NOTE_DELETED',
            user_id=deleted_by,
            entity_type='INTERNAL_NOTE',
            entity_id=note.id,
            category='MESSAGE_MANAGEMENT',
            metadata={
                'conversation_id': str(conversation.id),
                'provider_account_id': str(conversation.provider_account_id) if conversation.provider_account_id else None,
                'note_id': str(note.id),
                'body': note.body,
            },
        )
        self.db.commit()
