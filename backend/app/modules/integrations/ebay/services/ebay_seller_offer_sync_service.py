import logging
import re
from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy import func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.conversation import Conversation, Message, MessageSenderType
from app.models.ebay_account import EbayAccount
from app.models.offer import Offer, OfferStatus
from app.modules.integrations.ebay.services.ebay_offer_validation import (
    normalize_extracted_offer,
    update_missing_offer_fields,
)
from app.modules.integrations.ebay.oauth.token_service import EbayTokenService
from app.services.ebay_api_usage_service import EbayApiUsageService
from app.services.offer_consistency_service import OfferConsistencyService

logger = logging.getLogger(__name__)


class EbaySellerOfferSyncService:
    """
    Sync all offer notifications from My Messages.
    
    Handles:
    1. Seller-initiated offers ("Counteroffer submitted to buyer")
    2. Buyer-initiated offers ("You have a new offer")
    3. Buyer counteroffers ("Buyer made a counteroffer")
    """
    
    def __init__(self, db: Session):
        self.db = db
        self.tokens = EbayTokenService(db)
        self.api_usage = EbayApiUsageService(db)
    
    def sync_account(self, account_id: UUID, *, commit: bool = True) -> dict:
        """Fetch My Messages and extract all offer notifications."""
        
        # Get account first
        account = self.db.get(EbayAccount, account_id)
        processed_offers = set()

        logger.warning("🔔 ATTEMPTING SELLER OFFER SYNC FOR ACCOUNT: %s", account_id)
        
        if not account or not account.is_active:
            logger.error(f"❌ Account not found or inactive: {account_id}")
            raise ValueError('Active eBay account not found')
        
        logger.warning(f"✅ Account found: {account.ebay_username}")
        
        # Ensure valid token
        if not account.access_token or (
            account.access_token_expires_at and 
            account.access_token_expires_at <= datetime.now(UTC)
        ):
            logger.warning("🔄 Refreshing access token...")
            account = self.tokens.refresh_access_token(account.id)
            logger.warning("✅ Token refreshed")
        
        # Fetch messages with headers only
        logger.warning("📥 Fetching messages from GetMyMessages...")
        self.api_usage.reserve_calls(1)
        response = self.tokens.client.get_my_messages_raw(
            account.access_token,
            page_number=1,
            entries_per_page=200,
            detail_level="ReturnHeaders",
        )
        
        logger.warning(f"📊 Response status: {response.status_code}, OK: {response.ok}")
        
        if response.status_code == 401:
            logger.warning("🔄 Token expired, refreshing and retrying...")
            account = self.tokens.refresh_access_token(account.id)
            self.api_usage.reserve_calls(1)
            response = self.tokens.client.get_my_messages_raw(
                account.access_token,
                page_number=1,
                entries_per_page=200,
                detail_level="ReturnHeaders",
            )
            logger.warning(f"📊 Retry response status: {response.status_code}, OK: {response.ok}")
        
        if not response.ok:
            logger.error(f"❌ GetMyMessages failed: {response.payload}")
            raise RuntimeError(str(response.payload.get('error') if isinstance(response.payload, dict) else 'GetMyMessages failed'))
        
        payload = response.payload if isinstance(response.payload, dict) else {}
        messages = payload.get('messages', [])
        
        logger.warning(f"📨 Total messages from GetMyMessages: {len(messages)}")
        
        # Log first few messages for debugging
        for i, msg in enumerate(messages[:5]):
            logger.warning(f"  Message {i+1}: subject={msg.get('subject', '')[:50]}...")
        
        created = 0
        updated = 0
        matched = 0
        touched_conversation_ids = set()
        
        for msg in messages:
            subject = msg.get('subject', '')
            message_id = msg.get('message_id')
            if not message_id:
                continue

            # Skip if already processed in this batch (add this)
            if message_id in processed_offers:
                logger.debug(f"Skipping duplicate offer: {message_id}")
                continue
            processed_offers.add(message_id)

            # Check if this is an offer notification
            if not self._is_offer_notification(subject):
                continue
            
            logger.warning(f"🎯 Found offer notification: {subject[:100]}...")
            
            # Parse offer data from subject
            offer_data = self._parse_offer_from_subject(subject)
            if not offer_data:
                logger.warning(f"⚠️ Could not parse offer from subject: {subject}")
                continue
            
            logger.warning(f"📊 Parsed offer data: {offer_data}")
            
            # Extract item ID from the message
            item_id = msg.get('item_id') or offer_data.get('item_id')
            
            # Match to conversation
            conversation = self._match_conversation(
                account.id,
                item_id,
                offer_data.get('buyer'),
            )
            
            if not conversation and item_id and not offer_data.get('buyer'):
                # Use item-only matching only when eBay did not include a buyer and
                # the item identifies exactly one member conversation.
                conversation = self._match_unique_conversation_by_item_id(account.id, item_id)
            
            if not conversation:
                logger.warning(
                    '⚠️ Could not match offer to conversation: item=%s buyer=%s subject=%s',
                    item_id,
                    offer_data.get('buyer'),
                    subject[:100],
                )
                continue

            # --- ADD THIS CHECK ---
            if conversation.provider_conversation_type == 'FROM_EBAY':
                logger.warning(f"Skipping offer notification {message_id}: Conversation is FROM_EBAY")
                continue
            
            logger.warning(f"✅ Matched to conversation: {conversation.id}")
            matched += 1
            
            # Create or update system message
            sent_at = self._parse_datetime(msg.get('sent_date') or msg.get('receive_date'))
            if not sent_at:
                sent_at = datetime.now(UTC)
            
            # Build message body
            body = self._build_offer_message_body(offer_data, subject)
            buyer_username = offer_data.get('buyer') or conversation.buyer_identifier
            logger.warning(f"📝 Creating/updating message: {body[:100]}...")
            
            # *** FIX: Proper UPSERT logic ***
            # Check if message already exists by provider_message_id
            # Check if message already exists by provider_message_id ONLY
            existing = self.db.scalar(
                select(Message)
                .where(
                    Message.provider_message_id == message_id,
                )
            )

            if existing:
                # Update existing message
                existing.provider = 'EBAY'  # Ensure it's set correctly
                existing.body = body
                existing.sent_at = sent_at
                existing.raw_payload = msg
                existing.offer_data = {'notification_type': 'OFFER'}
                if existing.conversation_id != conversation.id:
                    existing.conversation_id = conversation.id
                offer_message = existing
                updated += 1
            else:
                # ✅ INSERT: Create new message
                logger.warning(f"✨ Creating new message: {message_id}")
                is_inbound = offer_data.get('direction') == 'INCOMING'
                message = Message(
                    conversation_id=conversation.id,
                    provider='EBAY',
                    provider_message_id=message_id,
                    sender_type=MessageSenderType.SYSTEM,
                    sender_identifier='eBay System',
                    recipient_identifier=account.ebay_username,
                    body=body,
                    is_inbound=is_inbound,
                    sent_at=sent_at,
                    raw_payload=msg,
                    offer_data={'notification_type': 'OFFER'},
                )
                
                self.db.add(message)
                self.db.flush()
                offer_message = message
                created += 1
                

            self._upsert_offer(
                account_id=account.id,
                conversation_id=conversation.id,
                offer_data={
                    **offer_data,
                    'buyer': buyer_username,
                },
                raw_msg=msg,
                message_id=offer_message.id,
            )
            touched_conversation_ids.add(conversation.id)
        
        logger.warning(f"📊 Final results: created={created}, updated={updated}, matched={matched}")
        
        OfferConsistencyService(self.db).sync_conversations(touched_conversation_ids)
        if commit:
            logger.warning("💾 Committing to database...")
            self.db.commit()
            logger.warning("✅ Commit complete")
        else:
            self.db.flush()
        
        return {
            'created': created,
            'updated': updated,
            'matched': matched,
            'total_messages': len(messages),
        }
    
    def _is_offer_notification(self, subject: str) -> bool:
        """Check if subject indicates any type of offer notification."""
        subject_lower = subject.lower()
        
        patterns = [
            'accepted an offer',
            'accepted your offer',
            'buyer accepted',
            'offer accepted',
            'counteroffer submitted to buyer',   # Seller sent counteroffer
            'you have a new offer',               # Buyer sent offer
            'buyer made a counteroffer',          # Buyer sent counteroffer
            'best offer',                         # General best offer
            'new offer for',                      # New offer notification
            'offer from',                         # Offer from buyer
            'offer submitted to',                 # Offer submitted
            'your offer on',        
            'sent an offer',              # Your offer
        ]
        
        return any(pattern in subject_lower for pattern in patterns)
    
    def _parse_offer_from_subject(self, subject: str) -> dict | None:
        """Parse offer details from subject line."""
        result = {}
        
        # Match actual money, not arbitrary numbers in item titles/models.
        currency_pattern = r'\b(?:(USD|EUR|GBP|AUD|CAD|JPY|INR|AU)\s+|US\s+)?\$([\d,]+(?:\.\d{1,2})?)\b|\b(USD|EUR|GBP|AUD|CAD|JPY|INR)\s+([\d,]+(?:\.\d{1,2})?)\b'
        amount_match = re.search(currency_pattern, subject)
        
        if amount_match:
            result['currency'] = self._normalize_currency(amount_match.group(1) or amount_match.group(3) or 'USD')
            raw_amount = amount_match.group(2) or amount_match.group(4)
            result['amount'] = Decimal(raw_amount.replace(',', ''))
        
        # Extract item ID from parentheses at end
        item_match = re.search(r'\(([0-9]+)\)\s*$', subject)
        if item_match:
            result['item_id'] = item_match.group(1)
        
        # Extract buyer username only when the subject explicitly includes one.
        # In subjects like "Counteroffer submitted to buyer: AUD $173.39 for ...",
        # the token after the colon is currency, not a username.
        buyer_match = re.search(r'\bbuyer\s+([a-zA-Z0-9_-]+)\b', subject, re.IGNORECASE)
        if buyer_match and buyer_match.group(1).lower() in {'made', 'accepted', 'sent'}:
            buyer_match = None
        if buyer_match:
            result['buyer'] = buyer_match.group(1)
        
        # Extract item title (between "for" and "(" or end)
        title_match = re.search(r'for\s+([^(]+?)(?:\s*\(|$)', subject)
        if title_match:
            result['item_title'] = title_match.group(1).strip()
        
        # Determine direction and type
        if "Counteroffer submitted to buyer" in subject:
            result['direction'] = 'OUTGOING'
            result['status'] = OfferStatus.PENDING
            result['offer_type'] = 'SELLER_COUNTEROFFER'
            result['display_type'] = 'You sent a counteroffer'
        elif "You have a new offer" in subject:
            result['direction'] = 'INCOMING'
            result['status'] = OfferStatus.PENDING
            result['offer_type'] = 'BUYER_OFFER'
            result['display_type'] = 'Buyer sent an offer'
        elif "Buyer made a counteroffer" in subject:
            result['direction'] = 'INCOMING'
            result['status'] = OfferStatus.PENDING
            result['offer_type'] = 'BUYER_COUNTEROFFER'
            result['display_type'] = 'Buyer sent a counteroffer'
        elif "accepted an offer" in subject.lower() or "offer accepted" in subject.lower():
            result['direction'] = 'INCOMING'
            result['status'] = OfferStatus.ACCEPTED
            result['offer_type'] = 'ACCEPTED_OFFER'
            result['display_type'] = 'accepted an offer'
        else:
            # Try to detect from context
            if any(word in subject.lower() for word in ['submitted to buyer', 'you sent']):
                result['direction'] = 'OUTGOING'
                result['display_type'] = 'You sent an offer'
            else:
                result['direction'] = 'INCOMING'
                result['display_type'] = 'New offer'
            result['status'] = OfferStatus.PENDING
            result['offer_type'] = 'OFFER'
        
        if 'amount' not in result and result.get('status') == OfferStatus.PENDING:
            return None
        
        return result
    
    def _build_offer_message_body(self, offer_data: dict, subject: str) -> str:
        """Build a formatted message body for display."""
        display_type = offer_data.get('display_type', 'Offer')
        amount = offer_data.get('amount')
        currency = offer_data.get('currency', 'USD')
        item_title = offer_data.get('item_title', '')
        buyer = offer_data.get('buyer', '')
        
        body = f"🔔 {display_type}: "
        
        if amount:
            body += f"{currency} {amount:,.2f}"
        
        if item_title:
            body += f" for {item_title}"
        
        if buyer:
            body += f" to {buyer}"
        
        return body
    
    def _match_conversation(self, account_id: UUID, item_id: str | None, buyer: str | None) -> Conversation | None:
        """Find conversation by item ID and/or buyer."""
        if not item_id and not buyer:
            return None

        item_id = str(item_id or '').strip()
        buyer = str(buyer or '').strip()
        
        base = select(Conversation).where(
            Conversation.provider_account_id == account_id,
            Conversation.provider_conversation_type == 'FROM_MEMBERS',
        )

        if item_id and buyer:
            statement = base.where(
                or_(
                    Conversation.reference_id == item_id,
                    Conversation.reference_id.like(f'%{item_id}%'),
                ),
                func.lower(Conversation.buyer_identifier) == buyer.lower(),
            ).order_by(Conversation.last_message_at.desc().nullslast())
            return self.db.scalar(statement.limit(1))

        if buyer:
            return self._match_unique_conversation_by_buyer(account_id, buyer)

        return self._match_unique_conversation_by_item_id(account_id, item_id)
    
    def _match_unique_conversation_by_item_id(self, account_id: UUID, item_id: str | None) -> Conversation | None:
        """Find a member conversation by item ID only when the match is unambiguous."""
        if not item_id:
            return None
        
        statement = select(Conversation).where(
            Conversation.provider_account_id == account_id,
            Conversation.provider_conversation_type == 'FROM_MEMBERS',
            or_(
                Conversation.reference_id == item_id,
                Conversation.reference_id.like(f'%{item_id}%')
            )
        ).order_by(Conversation.last_message_at.desc().nullslast())
        
        matches = list(self.db.scalars(statement.limit(2)))
        return matches[0] if len(matches) == 1 else None

    def _match_unique_conversation_by_buyer(self, account_id: UUID, buyer: str | None) -> Conversation | None:
        """Find a member conversation by buyer only when the match is unambiguous."""
        if not buyer:
            return None

        statement = (
            select(Conversation)
            .where(
                Conversation.provider_account_id == account_id,
                Conversation.provider_conversation_type == 'FROM_MEMBERS',
                func.lower(Conversation.buyer_identifier) == str(buyer).strip().lower(),
            )
            .order_by(Conversation.last_message_at.desc().nullslast())
        )

        matches = list(self.db.scalars(statement.limit(2)))
        return matches[0] if len(matches) == 1 else None
    
    def _upsert_offer(self, account_id: UUID, conversation_id: UUID, offer_data: dict, raw_msg: dict, message_id: UUID | None = None):
        """Create or update Offer record - check existing first."""
        self._fill_missing_notification_amount(account_id, conversation_id, offer_data)
        extracted_offer = {
            "provider_offer_id": raw_msg.get("message_id"),
            "listing_id": offer_data.get("item_id"),
            "buyer_username": offer_data.get("buyer"),
            "offer_amount": offer_data.get("amount"),
            "currency": offer_data.get("currency"),
            "status": offer_data.get("status"),
            "direction": offer_data.get("direction"),
            "offer_type": offer_data.get("offer_type"),
            "quantity": offer_data.get("quantity"),
            "raw_text": raw_msg.get("subject") or offer_data.get("item_title"),
            "created_at": datetime.now(UTC),
            "raw_payload": raw_msg,
        }
        normalized_offer, skip_reason = normalize_extracted_offer(
            extracted_offer,
            account=self.db.get(EbayAccount, account_id),
            logger=logger,
        )
        if skip_reason:
            logger.warning(
                "Skipping incomplete seller offer. reason=%s account_id=%s conversation_id=%s "
                "message_id=%s provider_offer_id=%s payload=%s",
                skip_reason,
                account_id,
                conversation_id,
                raw_msg.get("message_id"),
                extracted_offer.get("provider_offer_id"),
                extracted_offer,
            )
            return

        provider_offer_id = normalized_offer["provider_offer_id"]

        try:
            # Check if offer already exists
            existing = self.db.scalar(
                select(Offer).where(
                    Offer.provider_offer_id == provider_offer_id,
                    Offer.account_id == account_id,
                )
            )

            if existing:
                existing.conversation_id = conversation_id
                existing.message_id = message_id
                update_missing_offer_fields(existing, normalized_offer)
                logger.debug(f"Updated existing offer: {provider_offer_id}")
                return

            # Create new offer only after validation has populated required fields.
            offer = Offer(
                provider="EBAY",
                account_id=account_id,
                conversation_id=conversation_id,
                message_id=message_id,
                provider_offer_id=provider_offer_id,
                listing_id=normalized_offer.get("listing_id"),
                buyer_username=normalized_offer.get("buyer_username"),
                offer_amount=normalized_offer.get("offer_amount"),
                currency=normalized_offer.get("currency"),
                status=normalized_offer.get("status"),
                direction=normalized_offer.get("direction"),
                offer_type=normalized_offer.get("offer_type") or "OFFER",
                quantity=normalized_offer.get("quantity"),
                raw_text=normalized_offer.get("raw_text"),
                created_at=normalized_offer.get("created_at") or datetime.now(UTC),
                raw_payload=normalized_offer.get("raw_payload"),
            )
            self.db.add(offer)
            self.db.flush()
            logger.debug(f"Created new offer: {provider_offer_id}")
        except IntegrityError:
            self.db.rollback()
            logger.exception(
                "Seller offer upsert failed but sync will continue. account_id=%s conversation_id=%s "
                "message_id=%s provider_offer_id=%s payload=%s",
                account_id,
                conversation_id,
                raw_msg.get("message_id"),
                provider_offer_id,
                extracted_offer,
            )
        except Exception:
            self.db.rollback()
            logger.exception(
                "Unexpected seller offer upsert error but sync will continue. account_id=%s conversation_id=%s "
                "message_id=%s provider_offer_id=%s payload=%s",
                account_id,
                conversation_id,
                raw_msg.get("message_id"),
                provider_offer_id,
                extracted_offer,
            )

    def _fill_missing_notification_amount(self, account_id: UUID, conversation_id: UUID, offer_data: dict) -> None:
        if offer_data.get("amount") is not None:
            return
        if offer_data.get("status") not in {OfferStatus.ACCEPTED, OfferStatus.DECLINED, OfferStatus.EXPIRED}:
            return

        item_id = str(offer_data.get("item_id") or "").strip()
        buyer = str(offer_data.get("buyer") or "").strip().lower()
        statement = (
            select(Offer)
            .where(
                Offer.provider == "EBAY",
                Offer.account_id == account_id,
                Offer.conversation_id == conversation_id,
                Offer.offer_amount.is_not(None),
            )
            .order_by(Offer.created_at.desc())
        )

        candidates = list(self.db.scalars(statement.limit(10)))
        for offer in candidates:
            if item_id and offer.listing_id != item_id:
                continue
            if buyer and str(offer.buyer_username or "").strip().lower() != buyer:
                continue
            offer_data["amount"] = offer.offer_amount
            offer_data["currency"] = offer.currency
            if not offer_data.get("item_id"):
                offer_data["item_id"] = offer.listing_id
            if not offer_data.get("buyer"):
                offer_data["buyer"] = offer.buyer_username
            return

    def _parse_datetime(self, value: str | None) -> datetime | None:
        if not value:
            return None
        try:
            return datetime.fromisoformat(value.replace('Z', '+00:00'))
        except (ValueError, AttributeError):
            return None

    def _normalize_currency(self, value: str | None) -> str:
        normalized = str(value or 'USD').strip().upper()
        return {'AU': 'AUD'}.get(normalized, normalized)
