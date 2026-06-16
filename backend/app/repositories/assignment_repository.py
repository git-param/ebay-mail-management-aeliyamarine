from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.conversation import ConversationAssignment


class AssignmentRepository:
    def __init__(self, db: Session):
        self.db = db

    def get_current_assignment(self, conversation_id: UUID) -> ConversationAssignment | None:
        statement = (
            select(ConversationAssignment)
            .where(ConversationAssignment.conversation_id == conversation_id)
            .where(ConversationAssignment.unassigned_at.is_(None))
            .order_by(ConversationAssignment.assigned_at.desc())
        )
        return self.db.scalar(statement)

    def list_by_conversation(self, conversation_id: UUID) -> list[ConversationAssignment]:
        statement = (
            select(ConversationAssignment)
            .where(ConversationAssignment.conversation_id == conversation_id)
            .order_by(ConversationAssignment.assigned_at.desc())
        )
        return list(self.db.scalars(statement))

    def close_current_assignment(self, conversation_id: UUID) -> None:
        current_assignment = self.get_current_assignment(conversation_id)
        if current_assignment:
            current_assignment.unassigned_at = datetime.now(UTC)

    def add(self, assignment: ConversationAssignment) -> ConversationAssignment:
        self.db.add(assignment)
        return assignment
