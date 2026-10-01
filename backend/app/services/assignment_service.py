from datetime import UTC, datetime
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.models.conversation import ConversationAssignment
from app.models.user import User
from app.repositories.assignment_repository import AssignmentRepository
from app.services.conversation_service import ConversationService
from app.services.audit_service import AuditService


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
        commit: bool = True,
    ) -> ConversationAssignment:
        ConversationService(self.db).get_conversation(conversation_id)
        assignee = self.db.get(User, assigned_to)
        if not assignee or not assignee.is_active:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='Assignee not found')

        previous = self.repository.get_current_assignment(conversation_id)
        previous_assignee = previous.assigned_to if previous else None
        self.repository.close_current_assignment(conversation_id)
        assignment = ConversationAssignment(
            conversation_id=conversation_id,
            assigned_to=assigned_to,
            assigned_by=assigned_by,
        )
        self.repository.add(assignment)
        AuditService(self.db).log(action='CONVERSATION_ASSIGNED', user_id=assigned_by,
            entity_type='CONVERSATION', entity_id=conversation_id, category='ASSIGNMENT',
            metadata={'assigned_to': str(assigned_to), 'previous_assignee': str(previous_assignee) if previous_assignee else None})
        if commit:
            self.db.commit()
            self.db.refresh(assignment)
        else:
            self.db.flush()
        return assignment

    def unassign_conversation(
        self,
        *,
        conversation_id: UUID,
        actor_id: UUID | None = None,
    ) -> ConversationAssignment:
        ConversationService(self.db).get_conversation(conversation_id)
        assignment = self.repository.get_current_assignment(conversation_id)
        if not assignment:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail='Conversation is not currently assigned',
            )

        assignment.unassigned_at = datetime.now(UTC)
        AuditService(self.db).log(action='CONVERSATION_UNASSIGNED', user_id=actor_id,
            entity_type='CONVERSATION', entity_id=conversation_id, category='ASSIGNMENT',
            metadata={'previous_assignee': str(assignment.assigned_to)})
        self.db.commit()
        self.db.refresh(assignment)
        return assignment
