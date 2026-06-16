from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.models.conversation import ConversationAssignment
from app.models.user import User
from app.repositories.assignment_repository import AssignmentRepository
from app.services.conversation_service import ConversationService


class AssignmentService:
    def __init__(self, db: Session):
        self.db = db
        self.repository = AssignmentRepository(db)

    def assign_conversation(
        self,
        *,
        conversation_id: UUID,
        assigned_to: UUID,
        assigned_by: UUID,
    ) -> ConversationAssignment:
        ConversationService(self.db).get_conversation(conversation_id)
        assignee = self.db.get(User, assigned_to)
        if not assignee or not assignee.is_active:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='Assignee not found')

        self.repository.close_current_assignment(conversation_id)
        assignment = ConversationAssignment(
            conversation_id=conversation_id,
            assigned_to=assigned_to,
            assigned_by=assigned_by,
        )
        self.repository.add(assignment)
        self.db.commit()
        self.db.refresh(assignment)
        return assignment
