import logging
import re
from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.conversation import Conversation, Message, MessageSenderType
from app.models.ebay_account import EbayAccount
from app.models.offer import Offer, OfferDirection, OfferStatus
from app.modules.integrations.ebay.oauth.token_service import EbayTokenService
from app.services.ebay_api_usage_service import EbayApiUsageService

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
        
        logger.info("🔔 ATTEMPTING SELLER OFFER SYNC FOR ACCOUNT: %s", account_id)
        
        if not account or not account.is_active:
            logger.error(f"❌ Account not found or inactive: {account_id}")
            raise ValueError('Active eBay account not found')
        
        logger.info(f"✅ Account found: {account.ebay_username}")
        
        # Ensure valid token
        if not account.access_token or (
            account.access_token_expires_at and 
            account.access_token_expires_at <= datetime.now(UTC)
        ):
            logger.info("🔄 Refreshing access token...")
            account = self.tokens.refresh_access_token(account.id)
            logger.info("✅ Token refreshed")
        
        # Fetch messages with headers only
        logger.info("📥 Fetching messages from GetMyMessages...")
        self.api_usage.reserve_calls(1)
        response = self.tokens.client.get_my_messages_raw(
            account.access_token,
            page_number=1,
            entries_per_page=200,
            detail_level="ReturnHeaders",
        )
        
        logger.info(f"📊 Response status: {response.status_code}, OK: {response.ok}")
        
        if response.status_code == 401:
            logger.info("🔄 Token expired, refreshing and retrying...")
            account = self.tokens.refresh_access_token(account.id)
            self.api_usage.reserve_calls(1)
            response = self.tokens.client.get_my_messages_raw(
                account.access_token,
                page_number=1,
                entries_per_page=200,
                detail_level="ReturnHeaders",
            )
            logger.info(f"📊 Retry response status: {response.status_code}, OK: {response.ok}")
        
        if not response.ok:
            logger.error(f"❌ GetMyMessages failed: {response.payload}")
            raise RuntimeError(str(response.payload.get('error') if isinstance(response.payload, dict) else 'GetMyMessages failed'))
        
        payload = response.payload if isinstance(response.payload, dict) else {}
        messages = payload.get('messages', [])
        
        logger.info(f"📨 Total messages from GetMyMessages: {len(messages)}")
        
        # Log first few messages for debugging
        for i, msg in enumerate(messages[:5]):
            logger.info(f"  Message {i+1}: subject={msg.get('subject', '')[:50]}...")
        
        created = 0
        updated = 0
        matched = 0
        
        for msg in messages:
            subject = msg.get('subject', '')
            message_id = msg.get('message_id')
            
            # Check if this is an offer notification
            if not self._is_offer_notification(subject):
                continue
            
            logger.info(f"🎯 Found offer notification: {subject[:100]}...")
            
            # Parse offer data from subject
            offer_data = self._parse_offer_from_subject(subject)
            if not offer_data:
                logger.warning(f"⚠️ Could not parse offer from subject: {subject}")
                continue
            
            logger.info(f"📊 Parsed offer data: {offer_data}")
            
            # Extract item ID from the message
            item_id = msg.get('item_id') or offer_data.get('item_id')
            
            # Match to conversation
            conversation = self._match_conversation(
                account.id,
                item_id,
                offer_data.get('buyer'),
            )
            
            if not conversation:
                # Try to match by item_id only
                conversation = self._match_conversation_by_item_id(account.id, item_id)
            
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
                logger.info(f"Skipping offer notification {message_id}: Conversation is FROM_EBAY")
                continue
            
            logger.info(f"✅ Matched to conversation: {conversation.id}")
            
            # Create or update system message
            sent_at = self._parse_datetime(msg.get('sent_date') or msg.get('receive_date'))
            if not sent_at:
                sent_at = datetime.now(UTC)
            
            # Build message body
            body = self._build_offer_message_body(offer_data, subject)
            logger.info(f"📝 Creating/updating message: {body[:100]}...")
            
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
                if existing.conversation_id != conversation.id:
                    existing.conversation_id = conversation.id
                updated += 1
            else:
                # ✅ INSERT: Create new message
                logger.info(f"✨ Creating new message: {message_id}")
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
                )
                self.db.add(message)
                created += 1
        
        logger.info(f"📊 Final results: created={created}, updated={updated}, matched={matched}")
        
        if commit:
            logger.info("💾 Committing to database...")
            self.db.commit()
            logger.info("✅ Commit complete")
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
            'counteroffer submitted to buyer',   # Seller sent counteroffer
            'you have a new offer',               # Buyer sent offer
            'buyer made a counteroffer',          # Buyer sent counteroffer
            'best offer',                         # General best offer
            'new offer for',                      # New offer notification
            'offer from',                         # Offer from buyer
            'offer submitted to',                 # Offer submitted
            'your offer on',                      # Your offer
        ]
        
        return any(pattern in subject_lower for pattern in patterns)
    
    def _parse_offer_from_subject(self, subject: str) -> dict | None:
        """Parse offer details from subject line."""
        result = {}
        
        # Match any currency: "US $43.41", "$43.41", "EUR 116.23", "GBP 50.00", "JPY 5000"
        # Pattern: optional 3-letter currency code + space + amount
        currency_pattern = r'(?:([A-Z]{3})\s+)?(?:US\s+)?\$?([\d,]+\.?\d*)'
        amount_match = re.search(currency_pattern, subject)
        
        if amount_match:
            # If currency code is present, use it; otherwise default to USD
            result['currency'] = amount_match.group(1) if amount_match.group(1) else 'USD'
            result['amount'] = Decimal(amount_match.group(2).replace(',', ''))
        else:
            return None
        
        # Extract item ID from parentheses at end
        item_match = re.search(r'\(([0-9]+)\)\s*$', subject)
        if item_match:
            result['item_id'] = item_match.group(1)
        
        # Extract buyer username
        # Pattern for seller counteroffer: "Counteroffer submitted to buyer: US $43.41 for OMRON..."
        buyer_match = re.search(r'to buyer[:\s]+(?:US\s+\$[\d.]+ for )?([a-zA-Z0-9_-]+)', subject)
        if not buyer_match:
            # Pattern for buyer counteroffer: "Buyer made a counteroffer: US $23.00 for OMRON..."
            buyer_match = re.search(r'Buyer made a counteroffer[:\s]+(?:US\s+\$[\d.]+ for )?([a-zA-Z0-9_-]+)', subject)
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
        
        if 'amount' not in result:
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
        
        from sqlalchemy import or_
        
        statement = select(Conversation).where(
            Conversation.provider_account_id == account_id
        )
        
        conditions = []
        if item_id:
            # Try exact match on reference_id
            conditions.append(Conversation.reference_id == item_id)
            # Try partial match (eBay sometimes uses different formats)
            conditions.append(Conversation.reference_id.like(f'%{item_id}%'))
        
        if buyer:
            conditions.append(Conversation.buyer_identifier == buyer)
        
        if not conditions:
            return None
        
        statement = statement.where(or_(*conditions))
        statement = statement.order_by(Conversation.last_message_at.desc().nullslast())
        
        return self.db.scalar(statement.limit(1))
    
    def _match_conversation_by_item_id(self, account_id: UUID, item_id: str | None) -> Conversation | None:
        """Fallback: Find conversation by item ID only."""
        if not item_id:
            return None
        
        from sqlalchemy import or_
        
        statement = select(Conversation).where(
            Conversation.provider_account_id == account_id,
            or_(
                Conversation.reference_id == item_id,
                Conversation.reference_id.like(f'%{item_id}%')
            )
        ).order_by(Conversation.last_message_at.desc().nullslast())
        
        return self.db.scalar(statement.limit(1))
    
    def _upsert_offer(self, account_id: UUID, conversation_id: UUID, offer_data: dict, raw_msg: dict):
        """Create or update Offer record."""
        provider_offer_id = raw_msg.get('message_id')
        
        # Check if offer exists by provider_offer_id
        existing = self.db.scalar(
            select(Offer).where(
                Offer.provider_offer_id == provider_offer_id,
                Offer.account_id == account_id,
            )
        )
        
        if existing:
            # UPDATE existing offer
            logger.info(f"🔄 Updating existing offer: {provider_offer_id}")
            if offer_data.get('status'):
                existing.status = offer_data['status']
            existing.raw_payload = raw_msg
            return
        
        # Determine direction
        direction = OfferDirection.OUTGOING if offer_data.get('direction') == 'OUTGOING' else OfferDirection.INCOMING
        
        # CREATE new offer
        logger.info(f"✨ Creating new offer: {provider_offer_id}")
        offer = Offer(
            account_id=account_id,
            conversation_id=conversation_id,
            provider_offer_id=provider_offer_id,
            listing_id=offer_data.get('item_id'),
            buyer_username=offer_data.get('buyer'),
            offer_amount=offer_data.get('amount'),
            currency=offer_data.get('currency', 'USD'),
            status=offer_data.get('status', OfferStatus.PENDING),
            direction=direction,
            offer_type=offer_data.get('offer_type', 'OFFER'),
            message=offer_data.get('item_title', raw_msg.get('subject')),
            created_at=datetime.now(UTC),
            raw_payload=raw_msg,
        )
        self.db.add(offer)
    
    def _parse_datetime(self, value: str | None) -> datetime | None:
        if not value:
            return None
        try:
            return datetime.fromisoformat(value.replace('Z', '+00:00'))
        except (ValueError, AttributeError):
            return None