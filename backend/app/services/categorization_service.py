import logging
from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.models.category import Category
from app.models.conversation import Conversation
from app.services.category_service import OTHER_CATEGORY_NAME, normalize_keyword


logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class CategorizationResult:
    processed: int
    updated: int
    unchanged: int
    uncategorized: int


class CategorizationService:
    def __init__(self, db: Session):
        self.db = db

    def classify_text(self, text: str) -> UUID | None:
        normalized_text = f' {normalize_keyword(text)} '
        categories = list(
            self.db.scalars(
                select(Category)
                .options(selectinload(Category.keywords))
                .where(Category.is_active.is_(True))
                .order_by(Category.created_at.asc(), Category.id.asc())
            )
        )
        other_category_id = None
        for category in categories:
            if category.name.lower() == OTHER_CATEGORY_NAME.lower():
                other_category_id = category.id
            for keyword in category.keywords:
                normalized_keyword = normalize_keyword(keyword.keyword)
                if normalized_keyword and normalized_keyword in normalized_text:
                    return category.id
        return other_category_id

    def classify_conversation(self, conversation: Conversation) -> UUID | None:
        parts = [
            conversation.subject or '',
            conversation.buyer_identifier or '',
            conversation.reference_id or '',
            *(message.body for message in conversation.messages),
        ]
        return self.classify_text(' '.join(parts))

    def backfill_existing(self, *, batch_size: int = 250, only_uncategorized: bool = True) -> CategorizationResult:
        processed = updated = unchanged = uncategorized = 0
        offset = 0
        while True:
            statement = (
                select(Conversation)
                .options(selectinload(Conversation.messages))
                .order_by(Conversation.created_at.asc(), Conversation.id.asc())
                .offset(offset)
                .limit(batch_size)
            )
            if only_uncategorized:
                statement = statement.where(
                    Conversation.category_id.is_(None),
                    Conversation.category_manually_selected.is_(False),
                )
            conversations = list(self.db.scalars(statement))
            if not conversations:
                break
            for conversation in conversations:
                processed += 1
                if conversation.category_manually_selected:
                    unchanged += 1
                    continue
                category_id = self.classify_conversation(conversation)
                if category_id is None:
                    uncategorized += 1
                    unchanged += 1
                    continue
                if conversation.category_id == category_id:
                    unchanged += 1
                    continue
                conversation.category_id = category_id
                updated += 1
            self.db.commit()
            logger.info('Categorized batch processed=%s updated=%s', processed, updated)
            if only_uncategorized:
                offset = 0
            else:
                offset += batch_size
        return CategorizationResult(processed=processed, updated=updated, unchanged=unchanged, uncategorized=uncategorized)
