import logging

from sqlalchemy import select

from app.db.session import SessionLocal
from app.models.conversation import Conversation
from app.modules.integrations.ebay.providers import EBAY_PROVIDER_NAME
from app.services.conversation_product_context_service import ConversationProductContextService


logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def main() -> None:
    processed = 0
    enriched = 0
    with SessionLocal() as db:
        service = ConversationProductContextService(db)
        conversations = db.scalars(
            select(Conversation)
            .where(Conversation.provider == EBAY_PROVIDER_NAME)
            .where(Conversation.reference_type == 'LISTING')
            .where(Conversation.reference_id.is_not(None))
            .order_by(Conversation.created_at.asc())
        )
        for conversation in conversations:
            context = service.enrich_conversation(conversation)
            processed += 1
            if context and context.enrichment_status == 'ENRICHED':
                enriched += 1
            if processed % 50 == 0:
                db.commit()
                logger.warning('Product-context backfill processed=%s enriched=%s', processed, enriched)
        db.commit()
    logger.warning('Product-context backfill complete processed=%s enriched=%s', processed, enriched)


if __name__ == '__main__':
    main()
