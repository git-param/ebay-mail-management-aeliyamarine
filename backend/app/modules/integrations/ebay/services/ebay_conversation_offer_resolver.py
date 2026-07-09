from decimal import Decimal, InvalidOperation
import logging
import re

from sqlalchemy import and_, func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.conversation import Conversation, Message
from app.models.ebay_account import EbayAccount
from app.models.offer import Offer, OfferDirection, OfferStatus
from app.modules.integrations.ebay.services.ebay_offer_validation import (
    normalize_extracted_offer,
    update_missing_offer_fields,
)


logger = logging.getLogger(__name__)

OFFER_PHRASES = (
    "buyer sent an offer",
    "you have a new offer",
    "new offer for",
    "offer from",
    "sent an offer",
    "you sent an offer",
    "your offer on",
    "offer submitted to",
    "counteroffer submitted to buyer",
    "you sent a counteroffer",
    "buyer made a counteroffer",
    "sent a counteroffer",
    "accepted an offer",
    "accepted your offer",
    "buyer accepted",
    "offer accepted",
    "best offer accepted",
    "counteroffer accepted",
    "offer expired",
    "best offer expired",
    "counteroffer expired",
    "offer has expired",
    "counteroffer has expired",
    "offer declined",
    "declined your offer",
    "counteroffer declined",
)


class EbayConversationOfferResolver:
    def __init__(self, db: Session):
        self.db = db

    def resolve_for_conversation(self, conversation: Conversation) -> list[Offer]:
        if not self._can_process(conversation):
            self._clear_message_offer_data(conversation)
            return []

        account = self.db.get(EbayAccount, conversation.provider_account_id)
        if not account:
            return []

        offers_by_provider_id = {
            offer.provider_offer_id: offer
            for offer in self.db.scalars(
                select(Offer).where(
                    Offer.provider == "EBAY",
                    Offer.account_id == account.id,
                    Offer.conversation_id == conversation.id,
                )
            )
            if offer.provider_offer_id
        }

        reference_id = str(conversation.reference_id or "").strip()
        buyer_identifier = str(conversation.buyer_identifier or "").strip().lower()
        seen_offer_keys = set()

        # Attach existing synced offers to the synced conversation.
        # This handles offers created from eBay offer APIs where message_id is missing.
        if reference_id and buyer_identifier:
            existing_external_offers = list(
                self.db.scalars(
                    select(Offer).where(
                        Offer.provider == "EBAY",
                        Offer.account_id == account.id,
                        or_(
                            Offer.conversation_id == conversation.id,
                            and_(
                                Offer.listing_id == reference_id,
                                func.lower(func.coalesce(Offer.buyer_username, "")) == buyer_identifier,
                            ),
                            and_(
                                Offer.conversation_id.is_(None),
                                Offer.listing_id == reference_id,
                                Offer.buyer_username.is_(None),
                            ),
                        ),
                    )
                )
            )

            for offer in existing_external_offers:
                offer.conversation_id = conversation.id
                if not offer.buyer_username and conversation.buyer_identifier:
                    offer.buyer_username = conversation.buyer_identifier
                offers_by_provider_id[offer.provider_offer_id] = offer

        for message in conversation.messages:
            offer_data = self._extract_from_message(message, conversation, account)

            if not offer_data:
                message.offer_data = None
                continue

            extracted_offer = offer_data
            offer_data, skip_reason = normalize_extracted_offer(
                extracted_offer,
                message=message,
                account=account,
                logger=logger,
            )
            if skip_reason:
                self._log_skipped_offer(
                    skip_reason,
                    account=account,
                    conversation=conversation,
                    message=message,
                    payload=extracted_offer,
                )
                message.offer_data = None
                continue

            provider_offer_id = offer_data["provider_offer_id"]
            offer_key = ("EBAY", str(account.id), str(provider_offer_id))
            if offer_key in seen_offer_keys:
                logger.info("Skipping duplicate offer in same conversation parse: %s", offer_key)
                continue
            seen_offer_keys.add(offer_key)

            try:
                offer = self._upsert_offer_from_message(
                    account=account,
                    conversation=conversation,
                    message=message,
                    offer_data=offer_data,
                    offers_by_provider_id=offers_by_provider_id,
                )
            except IntegrityError:
                self.db.rollback()
                logger.warning(
                    "Offer upsert integrity failure but conversation offer resolution will continue. "
                    "account_id=%s conversation_id=%s message_id=%s provider_offer_id=%s payload=%s",
                    account.id,
                    conversation.id,
                    message.id,
                    provider_offer_id,
                    offer_data,
                )
                message.offer_data = None
                continue
            except Exception:
                self.db.rollback()
                logger.exception(
                    "Unexpected offer upsert error but conversation offer resolution will continue. "
                    "account_id=%s conversation_id=%s message_id=%s provider_offer_id=%s payload=%s",
                    account.id,
                    conversation.id,
                    message.id,
                    provider_offer_id,
                    offer_data,
                )
                message.offer_data = None
                continue

            message.offer_data = {
                "provider_offer_id": offer.provider_offer_id,
                "listing_id": offer.listing_id,
                "buyer_username": offer.buyer_username,
                "offer_amount": str(offer.offer_amount) if offer.offer_amount is not None else None,
                "amount": str(offer.offer_amount) if offer.offer_amount is not None else None,
                "currency": offer.currency,
                "status": offer.status,
                "direction": offer.direction,
                "offer_type": offer.offer_type,
                "message_id": str(message.id),
            }

        self.db.flush()

        return list(
            self.db.scalars(
                select(Offer)
                .where(
                    Offer.provider == "EBAY",
                    Offer.account_id == account.id,
                    Offer.conversation_id == conversation.id,
                )
                .order_by(Offer.created_at.asc())
            )
        )

    def _upsert_offer_from_message(
        self,
        *,
        account: EbayAccount,
        conversation: Conversation,
        message: Message,
        offer_data: dict,
        offers_by_provider_id: dict[str, Offer],
    ) -> Offer:
        provider_offer_id = offer_data["provider_offer_id"]
        account_id = account.id
        conversation_id = conversation.id
        message_id = message.id
        offer = offers_by_provider_id.get(provider_offer_id)

        if not offer:
            offer = self._existing_offer(account_id, provider_offer_id)

        if not offer:
            offer = Offer(
                provider="EBAY",
                account_id=account_id,
                conversation_id=conversation_id,
                message_id=message_id,
                provider_offer_id=provider_offer_id,
                listing_id=offer_data.get("listing_id"),
                buyer_username=offer_data.get("buyer_username"),
                offer_amount=offer_data.get("offer_amount"),
                currency=offer_data.get("currency"),
                status=offer_data.get("status"),
                direction=offer_data.get("direction"),
                offer_type=offer_data.get("offer_type"),
                quantity=offer_data.get("quantity"),
                raw_text=offer_data.get("raw_text"),
                raw_payload=offer_data.get("raw_payload"),
            )
            self.db.add(offer)
            try:
                self.db.flush()
            except IntegrityError:
                self.db.rollback()
                offer = self._existing_offer(account_id, provider_offer_id)
                if not offer:
                    raise
                logger.info(
                    "Recovered existing eBay offer after duplicate insert race account_id=%s "
                    "conversation_id=%s message_id=%s provider_offer_id=%s",
                    account_id,
                    conversation_id,
                    message_id,
                    provider_offer_id,
                )
                offer.conversation_id = conversation_id
                offer.message_id = message_id
                update_missing_offer_fields(offer, offer_data)
        else:
            offer.conversation_id = conversation_id
            offer.message_id = message_id
            update_missing_offer_fields(offer, offer_data)

        offers_by_provider_id[provider_offer_id] = offer
        self.db.flush()
        return offer

    def _existing_offer(self, account_id, provider_offer_id: str) -> Offer | None:
        return (
            self.db.query(Offer)
            .filter(
                Offer.provider == "EBAY",
                Offer.account_id == account_id,
                Offer.provider_offer_id == provider_offer_id,
            )
            .first()
        )

    def _log_skipped_offer(
        self,
        reason: str,
        *,
        account: EbayAccount,
        conversation: Conversation,
        message: Message,
        payload: dict | None,
    ) -> None:
        logger.warning(
            "Skipping incomplete eBay offer. reason=%s account_id=%s conversation_id=%s "
            "message_id=%s provider_offer_id=%s payload=%s",
            reason,
            account.id,
            conversation.id,
            message.id,
            payload.get("provider_offer_id") if payload else None,
            payload,
        )

    def _can_process(self, conversation: Conversation) -> bool:
        if not conversation:
            return False

        if (conversation.provider_conversation_type or "").upper() != "FROM_MEMBERS":
            return False

        if str(conversation.buyer_identifier or "").strip().lower() == "ebay":
            return False

        return True

    def _clear_message_offer_data(self, conversation: Conversation) -> None:
        for message in conversation.messages:
            message.offer_data = None
        self.db.flush()

    def _extract_from_message(self, message: Message, conversation: Conversation, account: EbayAccount) -> dict | None:
        raw_payload = message.raw_payload if isinstance(message.raw_payload, dict) else {}

        body = str(message.body or "")

        message_subject = str(
            raw_payload.get("subject")
            or raw_payload.get("Subject")
            or raw_payload.get("messageSubject")
            or raw_payload.get("title")
            or ""
        )

        conversation_payload = conversation.raw_payload if isinstance(conversation.raw_payload, dict) else {}
        summary_payload = conversation_payload.get("summary") if isinstance(conversation_payload.get("summary"), dict) else {}
        detail_payload = conversation_payload.get("detail") if isinstance(conversation_payload.get("detail"), dict) else {}

        conversation_subject = str(
            conversation.subject
            or summary_payload.get("conversationTitle")
            or detail_payload.get("conversationTitle")
            or ""
        )

        text = " ".join((conversation_subject, message_subject, body)).replace("\xa0", " ")
        text = " ".join(text.split())
        lower = text.lower()

        if not any(phrase in lower for phrase in OFFER_PHRASES):
            return None

        status = self._status(lower)
        amount, currency = self._extract_money(text)

        # Pending offers must have amount.
        # Accepted / expired / declined notifications may not always repeat the amount.
        if amount is None and status == OfferStatus.PENDING:
            return None

        listing_id = self._listing_id(raw_payload, message_subject, conversation, text)
        buyer_username = self._buyer_username(raw_payload, message, conversation, account)

        return {
            "provider_offer_id": str(
                raw_payload.get("offerId")
                or raw_payload.get("messageId")
                or raw_payload.get("message_id")
                or message.provider_message_id
                or f"msg:{message.id}"
            ),
            "listing_id": listing_id,
            "buyer_username": buyer_username,
            "offer_amount": amount,
            "currency": currency or "USD",
            "status": status,
            "direction": self._direction(lower, message),
            "offer_type": self._offer_type(lower),
            "quantity": self._quantity(raw_payload),
            "raw_text": text,
            "raw_payload": {
                "source": "on_demand_message_parse",
                "message_id": str(message.id),
                "provider_message_id": message.provider_message_id,
                "original_raw_payload": raw_payload,
            },
        }

    def _extract_money(self, text: str):
        patterns = (
            r"\b(?P<currency>USD|EUR|GBP|AUD|CAD|JPY|INR)\s*(?P<amount>[\d,]+(?:\.\d{1,2})?)",
            r"\bUS\s*\$\s*(?P<amount>[\d,]+(?:\.\d{1,2})?)",
            r"\$\s*(?P<amount>[\d,]+(?:\.\d{1,2})?)",
            r"€\s*(?P<amount>[\d,]+(?:\.\d{1,2})?)",
            r"£\s*(?P<amount>[\d,]+(?:\.\d{1,2})?)",
        )

        for pattern in patterns:
            match = re.search(pattern, text or "", re.IGNORECASE)
            if not match:
                continue

            amount = match.groupdict().get("amount")
            currency = match.groupdict().get("currency")

            if not currency:
                matched = match.group(0)
                if "€" in matched:
                    currency = "EUR"
                elif "£" in matched:
                    currency = "GBP"
                else:
                    currency = "USD"

            try:
                return Decimal(amount.replace(",", "")), currency.upper()
            except (InvalidOperation, AttributeError):
                return None, None

        return None, None

    def _listing_id(self, payload: dict, subject: str, conversation: Conversation, text: str | None = None) -> str | None:
        for key in ("itemId", "listingId", "item_id"):
            value = payload.get(key)
            if self._valid_listing_id(value):
                return str(value)

        # Example: subject ends with "(405712345678)"
        match = re.search(r"\((\d{9,15})\)\s*$", subject or "")
        if match:
            return match.group(1)

        # Example: https://www.ebay.com/itm/405712345678
        url_match = re.search(r"ebay\.com/itm/(\d{9,15})", text or "", re.IGNORECASE)
        if url_match:
            return url_match.group(1)

        # Fallback: any long eBay-like numeric ID in text
        any_long_id = re.search(r"\b(\d{9,15})\b", text or "")
        if any_long_id:
            return any_long_id.group(1)

        if (conversation.reference_type or "").upper() == "LISTING" and self._valid_listing_id(conversation.reference_id):
            return conversation.reference_id

        return None

    def _buyer_username(
        self,
        payload: dict,
        message: Message,
        conversation: Conversation,
        account: EbayAccount,
    ) -> str | None:
        buyer = payload.get("buyerUsername")
        if buyer and str(buyer).strip().lower() != "ebay":
            return str(buyer).strip()

        seller = str(account.ebay_username or "").strip().lower()

        if message.is_inbound:
            sender = str(message.sender_identifier or "").strip()
            if sender and sender.lower() not in ("ebay", seller):
                return sender

        buyer = str(conversation.buyer_identifier or "").strip()
        if buyer and buyer.lower() != "ebay":
            return buyer

        return None

    def _status(self, lower: str) -> str:
        if "accepted" in lower:
            return OfferStatus.ACCEPTED
        if "declined" in lower:
            return OfferStatus.DECLINED
        if "expired" in lower:
            return OfferStatus.EXPIRED
        return OfferStatus.PENDING

    def _direction(self, lower: str, message: Message) -> str:
        if any(phrase in lower for phrase in ("you sent", "submitted to buyer", "offer submitted to")):
            return OfferDirection.OUTGOING
        if any(
            phrase in lower
            for phrase in (
                "buyer sent",
                "buyer made",
                "you have a new offer",
                "new offer for",
                "offer from",
                "accepted an offer",
                "accepted your offer",
                "buyer accepted",
            )
        ):
            return OfferDirection.INCOMING
        return OfferDirection.INCOMING if message.is_inbound else OfferDirection.OUTGOING

    def _offer_type(self, lower: str) -> str:
        if "accepted" in lower:
            return "ACCEPTED_OFFER"
        if "counteroffer" in lower:
            return "COUNTEROFFER"
        return "OFFER"

    def _quantity(self, payload: dict) -> int:
        try:
            return int(payload.get("quantity") or 1)
        except (TypeError, ValueError):
            return 1

    def _valid_listing_id(self, value) -> bool:
        return bool(value and re.fullmatch(r"\d{9,15}", str(value).strip()))
