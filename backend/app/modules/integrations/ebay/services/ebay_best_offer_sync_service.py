import logging
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from uuid import UUID

from sqlalchemy import and_, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.conversation import Conversation
from app.models.ebay_account import EbayAccount
from app.models.offer import Offer, OfferDirection, OfferStatus
from app.modules.integrations.ebay.services.ebay_offer_validation import (
    normalize_extracted_offer,
    update_missing_offer_fields,
)
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
            

            logger.warning(
                "BestOffer API account_id=%s page=%s total_pages=%s offers_count=%s payload_keys=%s",
                account.id,
                page,
                payload.get("totalPages"),
                len(payload.get("offers", []) or []),
                list(payload.keys()),
            )

            for raw in payload.get('offers', []):
                conversation = None
                try:
                    conversation = self._match_conversation(
                        account.id,
                        raw.get('listingId'),
                        raw.get('buyerUsername'),
                    )

                    # Never skip saving the offer just because conversation was not found.
                    # Save it first, link it later from the conversation resolver.
                    if conversation and conversation.provider_conversation_type == 'FROM_EBAY':
                        logger.warning(
                            "Best offer %s matched FROM_EBAY conversation %s, saving offer without conversation link",
                            raw.get("offerId"),
                            conversation.id,
                        )
                        conversation = None

                    result, was_created = self._upsert(account, raw, conversation)

                    created += int(was_created)
                    updated += int(not was_created)
                    linked += int(result.conversation_id is not None)

                    if result.conversation_id:
                        conversation = self.db.get(Conversation, result.conversation_id)
                        if conversation and conversation.provider_conversation_type == 'FROM_EBAY':
                            logger.warning(f"Skipping offer {result.provider_offer_id} from FROM_EBAY conversation")
                            continue
                except IntegrityError:
                    self.db.rollback()
                    logger.exception(
                        "Best offer upsert failed but sync will continue. account_id=%s "
                        "conversation_id=%s message_id=%s provider_offer_id=%s payload=%s",
                        account.id,
                        getattr(conversation, "id", None),
                        None,
                        raw.get("offerId") if isinstance(raw, dict) else None,
                        raw,
                    )
                except ValueError as exc:
                    self.db.rollback()
                    logger.warning(
                        "Skipping incomplete best offer. reason=%s account_id=%s conversation_id=%s "
                        "message_id=%s provider_offer_id=%s payload=%s",
                        exc,
                        account.id,
                        getattr(conversation, "id", None),
                        None,
                        raw.get("offerId") if isinstance(raw, dict) else None,
                        raw,
                    )
                except Exception:
                    self.db.rollback()
                    logger.exception(
                        "Unexpected best offer upsert error but sync will continue. account_id=%s "
                        "conversation_id=%s message_id=%s provider_offer_id=%s payload=%s",
                        account.id,
                        getattr(conversation, "id", None),
                        None,
                        raw.get("offerId") if isinstance(raw, dict) else None,
                        raw,
                    )


            logger.warning(
                "BestOffer sync finished account_id=%s created=%s updated=%s linked=%s",
                account.id,
                created,
                updated,
                linked,
            )

            if page >= int(payload.get('totalPages') or 1):
                break
            page += 1
        if commit:
            self.db.commit()
        else:
            self.db.flush()
        return {'created': created, 'updated': updated, 'linked': linked}

    def _upsert(self, account: EbayAccount, raw: dict, conversation: Conversation | None) -> tuple[Offer, bool]:
        normalized_offer, skip_reason = normalize_extracted_offer(
            {
                "provider_offer_id": raw.get("offerId"),
                "listing_id": raw.get("listingId"),
                "buyer_username": raw.get("buyerUsername"),
                "offer_amount": self._decimal(raw.get("amount")),
                "currency": raw.get("currency"),
                "status": self._status(raw.get("status")),
                "direction": OfferDirection.INCOMING,
                "offer_type": raw.get("offerType"),
                "quantity": raw.get("quantity"),
                "raw_text": raw.get("buyerMessage"),
                "expires_at": self._datetime(raw.get("expirationTime")),
                "raw_payload": raw,
            },
            account=account,
            logger=logger,
        )
        if skip_reason:
            logger.warning(
                "Skipping incomplete best offer. reason=%s account_id=%s conversation_id=%s "
                "message_id=%s provider_offer_id=%s payload=%s",
                skip_reason,
                account.id,
                getattr(conversation, "id", None),
                None,
                raw.get("offerId"),
                raw,
            )
            raise ValueError(f"Skipping incomplete best offer: {skip_reason}")

        provider_id = normalized_offer["provider_offer_id"]
        listing_id = str(raw.get('listingId') or '').strip()

        if not provider_id or not listing_id:
            raise ValueError('GetBestOffers response omitted offer or listing ID')

        offer = self.db.scalar(
            select(Offer).where(
                Offer.provider == "EBAY",
                Offer.account_id == account.id,
                Offer.provider_offer_id == provider_id,
            )
        )
        created = offer is None

        if offer is None:
            offer = Offer(
                provider="EBAY",
                account_id=account.id,
                provider_offer_id=provider_id,
                listing_id=listing_id,
                conversation_id=conversation.id if conversation else None,
                buyer_username=normalized_offer.get("buyer_username"),
                offer_amount=normalized_offer.get("offer_amount"),
                currency=normalized_offer.get("currency"),
                status=normalized_offer.get("status"),
                direction=normalized_offer.get("direction"),
                offer_type=normalized_offer.get("offer_type"),
                quantity=normalized_offer.get("quantity"),
                raw_text=normalized_offer.get("raw_text"),
                expires_at=normalized_offer.get("expires_at"),
                raw_payload=normalized_offer.get("raw_payload"),
            )
            self.db.add(offer)

        # Use the passed conversation (already validated as FROM_MEMBERS)
        offer.provider = "EBAY"
        offer.account_id = account.id
        offer.conversation_id = conversation.id if conversation else None
        update_missing_offer_fields(
            offer,
            normalized_offer,
            fields=(
                "listing_id",
                "buyer_username",
                "offer_amount",
                "currency",
                "status",
                "direction",
                "offer_type",
                "quantity",
                "raw_text",
                "expires_at",
                "raw_payload",
            ),
        )

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
                        logger.warning(
                            'Created seller offer response message for conversation %s offer %s',
                            offer.conversation_id,
                            offer.provider_offer_id
                        )
        except Exception as e:
            logger.warning('Failed to sync seller offer response: %s', e)

    # In ebay_best_offer_sync_service.py
    def _match_conversation(self, account_id: UUID, listing_id: str, buyer: str) -> Conversation | None:
        buyer = str(buyer or '').strip()
        
        # Try to find by listing_id and buyer
        statement = (
            select(Conversation)
            .where(
                Conversation.provider_account_id == account_id,
                Conversation.reference_id == listing_id,
                Conversation.buyer_identifier == buyer
            )
        )
        conversation = self.db.scalar(statement)
        
        if conversation:
            return conversation
        
        # Try just by buyer
        statement = (
            select(Conversation)
            .where(
                Conversation.provider_account_id == account_id,
                Conversation.buyer_identifier == buyer
            )
            .order_by(Conversation.created_at.desc())
        )
        return self.db.scalar(statement)

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
