from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.models.category import Category
from app.models.conversation import Conversation, ConversationCategoryHistory, ConversationStatus, ConversationStatusHistory
from app.repositories.assignment_repository import AssignmentRepository
from app.repositories.conversation_category_history_repository import ConversationCategoryHistoryRepository
from app.repositories.conversation_repository import ConversationRepository
from app.repositories.conversation_status_history_repository import ConversationStatusHistoryRepository


class ConversationService:
    def __init__(self, db: Session):
        self.db = db
        self.repository = ConversationRepository(db)
        self.assignment_repository = AssignmentRepository(db)
        self.status_history_repository = ConversationStatusHistoryRepository(db)
        self.category_history_repository = ConversationCategoryHistoryRepository(db)

    def list_conversations(self, *, limit: int | None = None, offset: int = 0) -> list[Conversation]:
        return self.repository.list(limit=limit, offset=offset)

    def count_conversations(self) -> int:
        return self.repository.count()

    def get_conversation(self, conversation_id: UUID) -> Conversation:
        conversation = self.repository.get_by_id(conversation_id)
        if not conversation:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='Conversation not found')
        return conversation

    def get_current_assignee_id(self, conversation_id: UUID) -> UUID | None:
        assignment = self.assignment_repository.get_current_assignment(conversation_id)
        return assignment.assigned_to if assignment else None

    def update_status(
        self,
        *,
        conversation_id: UUID,
        new_status: ConversationStatus,
        changed_by: UUID,
        note: str | None = None,
    ) -> Conversation:
        conversation = self.get_conversation(conversation_id)
        old_status = conversation.status
        conversation.status = new_status
        self.status_history_repository.add(
            ConversationStatusHistory(
                conversation_id=conversation.id,
                old_status=old_status,
                new_status=new_status,
                changed_by=changed_by,
                note=note.strip() if note else None,
            )
        )
        self.db.commit()
        self.db.refresh(conversation)
        return conversation

    def update_category(
        self,
        *,
        conversation_id: UUID,
        category_id: UUID | None,
        changed_by: UUID,
        note: str | None = None,
    ) -> Conversation:
        conversation = self.get_conversation(conversation_id)
        if category_id and not self.db.get(Category, category_id):
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='Category not found')

        old_category_id = conversation.category_id
        conversation.category_id = category_id
        self.category_history_repository.add(
            ConversationCategoryHistory(
                conversation_id=conversation.id,
                old_category_id=old_category_id,
                new_category_id=category_id,
                changed_by=changed_by,
                note=note.strip() if note else None,
            )
        )
        self.db.commit()
        self.db.refresh(conversation)
        return conversation
