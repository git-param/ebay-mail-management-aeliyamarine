from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, Depends, status
from sqlalchemy.orm import Session

from app.api.dependencies import get_current_user, require_admin
from app.api.v1.routes.conversations import (
    visible_category_ids_for_user, visibility_user_id_for_user,
)
from app.db.session import SessionLocal, get_db
from app.modules.integrations.ebay.services.ebay_best_offer_sync_service import EbayBestOfferSyncService
from app.modules.integrations.ebay.services.ebay_negotiation_service import EbayNegotiationService
from app.schemas.offer import OfferResponse
from app.services.conversation_service import ConversationService


router = APIRouter()


@router.post('/sync/account/{account_id}', status_code=status.HTTP_202_ACCEPTED)
def sync_buyer_offers(account_id: UUID, background_tasks: BackgroundTasks, _=Depends(require_admin)):
    """Queue official Trading API BestOffer sync across all statuses."""
    background_tasks.add_task(_sync_buyer_offers, account_id)
    return {'status': 'queued', 'account_id': str(account_id), 'source': 'official_trading_get_best_offers_all'}


def _sync_buyer_offers(account_id: UUID) -> None:
    with SessionLocal() as db:
        EbayBestOfferSyncService(db).sync_account(account_id)


def _visible_conversation(conversation_id: UUID, db: Session, user):
    return ConversationService(db).get_conversation(
        conversation_id,
        visible_category_ids=visible_category_ids_for_user(db, user),
        visibility_user_id=visibility_user_id_for_user(user),
    )


@router.get('/conversation/{conversation_id}', response_model=list[OfferResponse])
def conversation_offers(conversation_id: UUID, db: Session = Depends(get_db), current_user=Depends(get_current_user)):
    _visible_conversation(conversation_id, db, current_user)
    return EbayNegotiationService(db).conversation_offers(conversation_id)
