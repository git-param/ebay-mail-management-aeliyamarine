# app/modules/integrations/ebay/services/ebay_offer_extraction_service.py

from __future__ import annotations

import re
from decimal import Decimal, InvalidOperation

from app.models.conversation import Conversation, Message
from app.models.offer import OfferDirection, OfferStatus


SUPPORTED_OFFER_PHRASES = (
    "buyer sent an offer",
    "you sent an offer",
    "you sent a counteroffer",
    "buyer made a counteroffer",
    "sent a counteroffer",
    "accepted an offer",
    "accepted your offer",
    "offer accepted",
)


def should_process_offer_for_conversation(conversation: Conversation | None) -> bool:
    if not conversation:
        return False

    if (conversation.provider_conversation_type or "").upper() != "FROM_MEMBERS":
        return False

    if str(conversation.buyer_identifier or "").strip().lower() == "ebay":
        return False

    return True


class EbayOfferExtractionService:
    def extract_from_message(self, message: Message, conversation: Conversation) -> dict | None:
        if not should_process_offer_for_conversation(conversation):
            return None

        payload = message.raw_payload if isinstance(message.raw_payload, dict) else {}

        if self._is_ebay_system_payload(payload, message):
            return None

        subject = self._first_text(
            payload.get("subject"),
            payload.get("Subject"),
            payload.get("messageSubject"),
            payload.get("title"),
        )
        body = self._first_text(
            message.body,
            payload.get("messageBody"),
            payload.get("body"),
            payload.get("text"),
        )

        text = self._clean(" ".join(part for part in (subject, body) if part))
        lower = text.lower()

        if not any(phrase in lower for phrase in SUPPORTED_OFFER_PHRASES):
            return None

        amount, currency = self._extract_money(text)
        if amount is None:
            return None

        listing_id = self._extract_listing_id(payload, subject, conversation)
        buyer_username = self._extract_buyer_username(payload, message, conversation)

        signal = self._detect_signal(lower, message)

        return {
            "provider_offer_id": self._provider_offer_id(payload, message),
            "listing_id": listing_id,
            "buyer_username": buyer_username,
            "offer_amount": amount,
            "currency": currency or "USD",
            "status": signal["status"],
            "direction": signal["direction"],
            "offer_type": signal["offer_type"],
            "quantity": self._safe_int(payload.get("quantity"), default=1),
            "raw_text": text,
            "raw_payload": {
                "source": "conversation_detail_on_demand",
                "provider_message_id": message.provider_message_id,
                "message_id": str(message.id),
                "original_raw_payload": payload,
            },
        }

    def _is_ebay_system_payload(self, payload: dict, message: Message) -> bool:
        conversation_type = str(payload.get("conversationType") or payload.get("conversation_type") or "").upper()
        if conversation_type == "FROM_EBAY":
            return True

        sender = str(
            payload.get("senderUsername")
            or payload.get("sender_username")
            or message.sender_identifier
            or ""
        ).strip().lower()

        return sender == "ebay"

    def _extract_listing_id(self, payload: dict, subject: str | None, conversation: Conversation) -> str | None:
        value = self._first_text(
            payload.get("itemId"),
            payload.get("item_id"),
            payload.get("listingId"),
            payload.get("listing_id"),
        )

        if self._is_valid_ebay_item_id(value):
            return value

        subject_match = re.search(r"\((\d{9,15})\)\s*$", subject or "")
        if subject_match:
            return subject_match.group(1)

        if (conversation.reference_type or "").upper() == "LISTING" and self._is_valid_ebay_item_id(conversation.reference_id):
            return conversation.reference_id

        return None

    def _extract_buyer_username(self, payload: dict, message: Message, conversation: Conversation) -> str | None:
        value = self._first_text(
            payload.get("buyerUsername"),
            payload.get("buyer_username"),
            payload.get("buyer"),
        )

        if value and value.lower() != "ebay":
            return value

        if message.is_inbound and message.sender_identifier and message.sender_identifier.lower() != "ebay":
            return message.sender_identifier

        if conversation.buyer_identifier and conversation.buyer_identifier.lower() != "ebay":
            return conversation.buyer_identifier

        return None

    def _provider_offer_id(self, payload: dict, message: Message) -> str:
        return str(
            payload.get("offerId")
            or payload.get("offer_id")
            or payload.get("responseId")
            or payload.get("messageId")
            or message.provider_message_id
            or f"msg:{message.id}"
        )

    def _detect_signal(self, lower: str, message: Message) -> dict:
        if "accepted an offer" in lower or "accepted your offer" in lower or "offer accepted" in lower:
            return {
                "status": OfferStatus.ACCEPTED,
                "direction": OfferDirection.INCOMING if message.is_inbound else OfferDirection.OUTGOING,
                "offer_type": "ACCEPTED_OFFER",
            }

        if "you sent a counteroffer" in lower or "you sent an offer" in lower:
            return {
                "status": OfferStatus.PENDING,
                "direction": OfferDirection.OUTGOING,
                "offer_type": "SELLER_COUNTEROFFER",
            }

        if "sent a counteroffer" in lower or "buyer made a counteroffer" in lower:
            return {
                "status": OfferStatus.PENDING,
                "direction": OfferDirection.INCOMING,
                "offer_type": "BUYER_COUNTEROFFER",
            }

        return {
            "status": OfferStatus.PENDING,
            "direction": OfferDirection.INCOMING,
            "offer_type": "BUYER_OFFER",
        }

    def _extract_money(self, text: str) -> tuple[Decimal | None, str | None]:
        patterns = (
            r"\b(?P<currency>USD|EUR|GBP|AUD|CAD|JPY|INR)\s*(?P<amount>[\d,]+(?:\.\d{1,2})?)",
            r"\b(?P<currency>AU)\s*\$\s*(?P<amount>[\d,]+(?:\.\d{1,2})?)",
            r"\bUS\s*\$\s*(?P<amount>[\d,]+(?:\.\d{1,2})?)",
            r"\$\s*(?P<amount>[\d,]+(?:\.\d{1,2})?)",
            r"€\s*(?P<amount>[\d,]+(?:\.\d{1,2})?)",
            r"£\s*(?P<amount>[\d,]+(?:\.\d{1,2})?)",
        )

        for pattern in patterns:
            match = re.search(pattern, text or "", re.IGNORECASE)
            if not match:
                continue

            raw_amount = match.groupdict().get("amount")
            raw_currency = match.groupdict().get("currency")

            matched_text = match.group(0)
            if not raw_currency:
                if "€" in matched_text:
                    raw_currency = "EUR"
                elif "£" in matched_text:
                    raw_currency = "GBP"
                else:
                    raw_currency = "USD"

            try:
                normalized_currency = raw_currency.upper()
                if normalized_currency == "AU":
                    normalized_currency = "AUD"
                return Decimal(raw_amount.replace(",", "")), normalized_currency
            except (InvalidOperation, AttributeError):
                return None, None

        return None, None

    def _is_valid_ebay_item_id(self, value: str | None) -> bool:
        return bool(value and re.fullmatch(r"\d{9,15}", str(value).strip()))

    def _safe_int(self, value, default: int = 1) -> int:
        try:
            return int(value or default)
        except (TypeError, ValueError):
            return default

    def _clean(self, value: str | None) -> str:
        return " ".join(str(value or "").replace("\xa0", " ").split())

    def _first_text(self, *values) -> str | None:
        for value in values:
            if value is not None and str(value).strip():
                return str(value).strip()
        return None
