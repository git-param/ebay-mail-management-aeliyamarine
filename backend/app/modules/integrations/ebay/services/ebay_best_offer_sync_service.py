import logging
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from uuid import UUID

from sqlalchemy import and_, or_, select
from sqlalchemy.orm import Session

from app.models.conversation import Conversation
from app.models.ebay_account import EbayAccount
from app.models.offer import Offer, OfferDirection, OfferStatus
from app.models.order_context import ConversationProductContext
from app.modules.integrations.ebay.oauth.token_service import EbayTokenService
from app.services.ebay_api_usage_service import EbayApiUsageService

logger = logging.getLogger(__name__)


class EbayBestOfferSyncService:
    """Poll Trading API offers and materialize them without slowing conversation reads."""

    def __init__(self, db: Session):
        self.db = db
        self.tokens = EbayTokenService(db)
        self.api_usage = EbayApiUsageService(db)

    def sync_account(self, account_id: UUID, *, commit: bool = True) -> dict[str, int]:
        account = self.db.get(EbayAccount, account_id)
        if not account or not account.is_active:
            raise ValueError('Active eBay account not found')
        if not account.access_token or (account.access_token_expires_at and account.access_token_expires_at <= datetime.now(UTC)):
            account = self.tokens.refresh_access_token(account.id)

        created = updated = linked = 0
        page = 1
        while True:
            self.api_usage.reserve_calls(1)
            response = self.tokens.client.get_best_offers_raw(account.access_token, page=page)
            if response.status_code == 401:
                account = self.tokens.refresh_access_token(account.id)
                self.api_usage.reserve_calls(1)
                response = self.tokens.client.get_best_offers_raw(account.access_token, page=page)
            if not response.ok:
                raise RuntimeError(str(response.payload.get('error') if isinstance(response.payload, dict) else 'GetBestOffers failed'))
            payload = response.payload if isinstance(response.payload, dict) else {}
            for raw in payload.get('offers', []):
                result, was_created = self._upsert(account, raw)
                created += int(was_created)
                updated += int(not was_created)
                linked += int(result.conversation_id is not None)
                
                # Also sync the seller's offer response if present
                if result.conversation_id:
                    self._sync_seller_offer_response(account, result)
                    
            if page >= int(payload.get('totalPages') or 1):
                break
            page += 1
        if commit:
            self.db.commit()
        else:
            self.db.flush()
        return {'created': created, 'updated': updated, 'linked': linked}

    def _upsert(self, account: EbayAccount, raw: dict) -> tuple[Offer, bool]:
        provider_id = str(raw.get('offerId') or '').strip()
        listing_id = str(raw.get('listingId') or '').strip()
        if not provider_id or not listing_id:
            raise ValueError('GetBestOffers response omitted offer or listing ID')
        offer = self.db.scalar(select(Offer).where(Offer.provider_offer_id == provider_id))
        created = offer is None
        if offer is None:
            offer = Offer(provider_offer_id=provider_id, listing_id=listing_id, raw_payload=raw)
            self.db.add(offer)
        conversation = self._match_conversation(account.id, listing_id, raw.get('buyerUsername'))
        offer.account_id = account.id
        offer.conversation_id = conversation.id if conversation else None
        offer.buyer_username = raw.get('buyerUsername')
        offer.offer_amount = self._decimal(raw.get('amount'))
        offer.currency = raw.get('currency')
        offer.status = self._status(raw.get('status'))
        offer.direction = OfferDirection.INCOMING
        offer.offer_type = raw.get('offerType')
        offer.quantity = int(raw.get('quantity') or 1)
        offer.message = raw.get('buyerMessage')
        offer.expires_at = self._datetime(raw.get('expirationTime'))
        offer.raw_payload = raw
        if created and conversation:
            matching_message = next((
                message for message in reversed(conversation.messages)
                if message.is_inbound
                and (not offer.message or message.body.strip() == offer.message.strip())
            ), None)
            if matching_message:
                offer.created_at = matching_message.sent_at
        return offer, created
    
    def _sync_seller_offer_response(self, account: EbayAccount, offer: Offer):
        """
        Sync the seller's response to an offer if it exists.
        This creates a message in the conversation with the seller's offer details.
        """
        try:
            # Get the offer details from eBay to check for seller responses
            self.api_usage.reserve_calls(1)
            response = self.tokens.client.get_offer_details_raw(
                account.access_token,
                offer_id=offer.provider_offer_id
            )
            
            if response.status_code == 401:
                account = self.tokens.refresh_access_token(account.id)
                self.api_usage.reserve_calls(1)
                response = self.tokens.client.get_offer_details_raw(
                    account.access_token,
                    offer_id=offer.provider_offer_id
                )
            
            if response.ok and isinstance(response.payload, dict):
                offer_detail = response.payload
                
                # Check if seller responded with a counter-offer
                if 'sellerResponse' in offer_detail:
                    seller_response = offer_detail['sellerResponse']
                    
                    # Create or update the seller's offer message
                    from app.models.message import Message
                    from app.models.message_direction import MessageDirection
                    
                    # Check if we already have a message for this response
                    existing_message = self.db.scalar(
                        select(Message).where(
                            Message.conversation_id == offer.conversation_id,
                            Message.provider_message_id == seller_response.get('responseId'),
                            Message.sender_type == 'SELLER'
                        )
                    )
                    
                    if not existing_message:
                        seller_message = Message(
                            conversation_id=offer.conversation_id,
                            provider_message_id=seller_response.get('responseId'),
                            sender_type='SELLER',
                            sender_identifier=account.ebay_username,
                            body=seller_response.get('message', f"Counter-offer: ${seller_response.get('amount')}"),
                            is_inbound=False,  # Outgoing from seller
                            direction=MessageDirection.OUTGOING,
                            sent_at=self._datetime(seller_response.get('createdDate')) or datetime.now(UTC),
                            raw_payload=seller_response,
                        )
                        self.db.add(seller_message)
                        
                        # Also store the offer details in the message metadata
                        seller_message.offer_data = {
                            'type': 'SELLER_OFFER',
                            'amount': float(seller_response.get('amount', 0)),
                            'status': seller_response.get('status', 'PENDING'),
                            'currency': seller_response.get('currency', 'USD'),
                            'message': seller_response.get('message', ''),
                        }
                        logger.info(
                            'Created seller offer response message for conversation %s offer %s',
                            offer.conversation_id,
                            offer.provider_offer_id
                        )
        except Exception as e:
            logger.warning('Failed to sync seller offer response: %s', e)

    def _match_conversation(self, account_id: UUID, listing_id: str, buyer) -> Conversation | None:
        buyer = str(buyer or '').strip()
        listing_match = or_(
            Conversation.reference_id == listing_id,
            ConversationProductContext.reference_id == listing_id,
        )
        statement = (
            select(Conversation).outerjoin(ConversationProductContext)
            .where(Conversation.provider_account_id == account_id, listing_match)
        )
        if buyer:
            statement = statement.where(Conversation.buyer_identifier == buyer)
        matches = list(self.db.scalars(statement.limit(2)))
        return matches[0] if len(matches) == 1 else None

    def _status(self, value) -> OfferStatus:
        normalized = str(value or 'Pending').upper()
        return {
            'ACTIVE': OfferStatus.PENDING, 'PENDING': OfferStatus.PENDING,
            'ACCEPTED': OfferStatus.ACCEPTED, 'DECLINED': OfferStatus.DECLINED,
            'EXPIRED': OfferStatus.EXPIRED,
        }.get(normalized, OfferStatus.PENDING)

    def _decimal(self, value):
        try:
            return Decimal(str(value)) if value is not None else None
        except InvalidOperation:
            return None

    def _datetime(self, value):
        try:
            return datetime.fromisoformat(str(value).replace('Z', '+00:00')) if value else None
        except ValueError:
            return None