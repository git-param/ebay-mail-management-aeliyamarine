from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.conversation import ConversationParticipant


class ConversationParticipantRepository:
    def __init__(self, db: Session):
        self.db = db

    def list_by_conversation(self, conversation_id: UUID) -> list[ConversationParticipant]:
        statement = (
            select(ConversationParticipant)
            .where(ConversationParticipant.conversation_id == conversation_id)
            .order_by(ConversationParticipant.created_at.asc())
        )
        return list(self.db.scalars(statement))

    def get_by_identity(
        self,
        *,
        conversation_id: UUID,
        participant_identifier: str,
        participant_type: str,
    ) -> ConversationParticipant | None:
        statement = (
            select(ConversationParticipant)
            .where(ConversationParticipant.conversation_id == conversation_id)
            .where(ConversationParticipant.participant_identifier == participant_identifier)
            .where(ConversationParticipant.participant_type == participant_type)
        )
        return self.db.scalar(statement)

    def add(self, participant: ConversationParticipant) -> ConversationParticipant:
        self.db.add(participant)
        return participant
