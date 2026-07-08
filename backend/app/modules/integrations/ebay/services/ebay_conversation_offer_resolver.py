from decimal import Decimal, InvalidOperation
import re

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.conversation import Conversation, Message
from app.models.ebay_account import EbayAccount
from app.models.offer import Offer, OfferDirection, OfferStatus


OFFER_PHRASES = (
    "sent an offer",
    "sent a counteroffer",
    "accepted an offer",
    "accepted your offer",
    "offer accepted",
    "you sent an offer",
    "you sent a counteroffer",
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
                    Offer.account_id == conversation.provider_account_id,
                    Offer.conversation_id == conversation.id,
                )
            )
            if offer.provider_offer_id
        }

        for message in conversation.messages:
            offer_data = self._extract_from_message(message, conversation, account)

            if not offer_data:
                message.offer_data = None
                continue

            provider_offer_id = offer_data["provider_offer_id"]
            offer = offers_by_provider_id.get(provider_offer_id)

            if not offer:
                offer = self.db.scalar(
                    select(Offer).where(
                        Offer.provider == "EBAY",
                        Offer.account_id == account.id,
                        Offer.provider_offer_id == provider_offer_id,
                    )
                )

            if not offer:
                offer = Offer(
                    provider="EBAY",
                    account_id=account.id,
                    conversation_id=conversation.id,
                    message_id=message.id,
                    provider_offer_id=provider_offer_id,
                )
                self.db.add(offer)

            offers_by_provider_id[provider_offer_id] = offer

            offer.message_id = message.id
            offer.listing_id = offer_data["listing_id"]
            offer.buyer_username = offer_data["buyer_username"]
            offer.offer_amount = offer_data["offer_amount"]
            offer.currency = offer_data["currency"]
            offer.status = offer_data["status"]
            offer.direction = offer_data["direction"]
            offer.offer_type = offer_data["offer_type"]
            offer.quantity = offer_data["quantity"]
            offer.raw_text = offer_data["raw_text"]
            offer.raw_payload = offer_data["raw_payload"]

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
                .where(Offer.conversation_id == conversation.id)
                .order_by(Offer.created_at.asc())
            )
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

        sender = str(
            raw_payload.get("senderUsername")
            or raw_payload.get("sender_username")
            or message.sender_identifier
            or ""
        ).strip().lower()

        # if sender == "ebay":
        #     return None

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

        amount, currency = self._extract_money(text)
        if amount is None:
            return None

        listing_id = self._listing_id(raw_payload, message_subject, conversation, text)
        buyer_username = self._buyer_username(raw_payload, message, conversation, account)

        return {
            "provider_offer_id": str(
                raw_payload.get("offerId")
                or raw_payload.get("offer_id")
                or raw_payload.get("messageId")
                or message.provider_message_id
                or f"msg:{message.id}"
            ),
            "listing_id": listing_id,
            "buyer_username": buyer_username,
            "offer_amount": amount,
            "currency": currency or "USD",
            "status": self._status(lower),
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
        for key in ("itemId", "item_id", "listingId", "listing_id"):
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
        for key in ("buyerUsername", "buyer_username", "buyer"):
            value = payload.get(key)
            if value and str(value).strip().lower() != "ebay":
                return str(value).strip()

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
        if "you sent" in lower:
            return OfferDirection.OUTGOING
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