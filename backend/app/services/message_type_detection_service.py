import re
from collections import Counter
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.models.conversation import Conversation
from app.models.message_type import MessageType


def normalize_message_type_text(value: str) -> str:
    return re.sub(r'\s+', ' ', re.sub(r'[^\w\s]', ' ', value.lower(), flags=re.UNICODE)).strip()


class MessageTypeDetectionService:
    """Suggest a reply Message Type from the latest conversation messages."""

    def __init__(self, db: Session):
        self.db = db

    @staticmethod
    def score(text: str, message_types: list[MessageType]) -> Counter:
        normalized_text = f' {normalize_message_type_text(text)} '
        scores: Counter = Counter()
        for message_type in message_types:
            for keyword in message_type.keywords:
                normalized_keyword = normalize_message_type_text(keyword.keyword)
                if normalized_keyword:
                    scores[message_type.id] += normalized_text.count(f' {normalized_keyword} ')
        return scores

    def suggest(self, conversation: Conversation) -> UUID | None:
        message_types = list(
            self.db.scalars(
                select(MessageType)
                .options(selectinload(MessageType.keywords))
                .where(MessageType.is_active.is_(True), MessageType.is_deleted.is_(False))
            )
        )
        latest_messages = sorted(
            conversation.messages,
            key=lambda message: (message.sent_at, str(message.id)),
            reverse=True,
        )[:4]
        scores = self.score(' '.join(message.body or '' for message in latest_messages), message_types)
        highest = max(scores.values(), default=0)
        winners = [message_type_id for message_type_id, value in scores.items() if value == highest and value > 0]
        return winners[0] if len(winners) == 1 else None
