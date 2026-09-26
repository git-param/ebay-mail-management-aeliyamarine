from uuid import UUID

from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.api.dependencies import get_current_user, require_admin
from app.db.session import get_db
from app.modules.integrations.ebay.services.ebay_negotiation_service import EbayNegotiationService
from app.schemas.offer import OfferResponse
from app.services.conversation_service import ConversationService


router = APIRouter()


@router.post('/sync/account/{account_id}', status_code=status.HTTP_202_ACCEPTED)
def sync_buyer_offers(account_id: UUID, db: Session = Depends(get_db), user=Depends(require_admin)):
    """Legacy endpoint shares the safe spawned Best Offer job dispatcher."""
    from app.services.ebay_best_offer_job_service import EbayBestOfferJobService
    from app.services.ebay_best_offer_worker import dispatch
    return dispatch(EbayBestOfferJobService(db).reserve([account_id], user=user))


def _visible_conversation(conversation_id: UUID, db: Session, user):
    return ConversationService(db).get_conversation(
        conversation_id,
    )


@router.get('/conversation/{conversation_id}', response_model=list[OfferResponse])
def conversation_offers(conversation_id: UUID, db: Session = Depends(get_db), current_user=Depends(get_current_user)):
    _visible_conversation(conversation_id, db, current_user)
    return EbayNegotiationService(db).conversation_offers(conversation_id)
