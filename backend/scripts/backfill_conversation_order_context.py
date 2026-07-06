import logging

from sqlalchemy import select

from app.db.session import SessionLocal
from app.models.conversation import Conversation
from app.modules.integrations.ebay.providers import EBAY_PROVIDER_NAME
from app.services.order_context_service import OrderContextService


logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def main() -> None:
    processed = 0
    linked = 0
    with SessionLocal() as db:
        service = OrderContextService(db)
        conversations = db.scalars(
            select(Conversation)
            .where(Conversation.provider == EBAY_PROVIDER_NAME)
            .order_by(Conversation.created_at.asc())
        )
        for conversation in conversations:
            mapping = service.link_conversation_context(conversation=conversation)
            processed += 1
            if mapping.ebay_order_id:
                linked += 1
            if processed % 100 == 0:
                db.commit()
                logger.warning('Backfilled %s conversations, linked %s order contexts', processed, linked)
        db.commit()
    logger.warning('Backfill complete. processed=%s linked=%s', processed, linked)


if __name__ == '__main__':
    main()
