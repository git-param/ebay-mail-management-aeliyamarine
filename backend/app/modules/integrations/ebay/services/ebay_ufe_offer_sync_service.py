from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.conversation import Conversation, Message, MessageSenderType
from app.models.ebay_account import EbayAccount
from app.models.offer import Offer, OfferDirection, OfferStatus
from app.services.offer_consistency_service import OfferConsistencyService


class EbayUfeOfferSyncService:
    """Persist offer cards from eBay's rendered member conversation payload."""

    def __init__(self, db: Session):
        self.db = db

    def sync_conversation_payload(self, account: EbayAccount, conversation: Conversation, payload: dict) -> int:
        cards = self.extract_offer_cards(payload, conversation)
        if not cards:
            return 0

        for offer in list(
            self.db.scalars(select(Offer).where(Offer.conversation_id == conversation.id))
        ):
            self.db.delete(offer)
        self.db.flush()

        for card in cards:
            message = self._upsert_offer_message(account, conversation, card)
            self.db.add(
                Offer(
                    provider="EBAY",
                    account_id=account.id,
                    conversation_id=conversation.id,
                    message_id=message.id,
                    provider_offer_id=card["provider_offer_id"],
                    listing_id=conversation.reference_id,
                    buyer_username=conversation.buyer_identifier,
                    offer_amount=card["amount"],
                    currency=card["currency"],
                    status=card["status"],
                    direction=card["direction"],
                    offer_type=card["offer_type"],
                    quantity=1,
                    raw_text=card["label"],
                    raw_payload={"source": "ufe_conversation_offer_card", "card": card["raw"]},
                    created_at_provider=card["sent_at"],
                    created_at=card["sent_at"],
                )
            )

        self.db.flush()
        OfferConsistencyService(self.db).sync_conversation(conversation.id)
        return len(cards)

    def extract_offer_cards(self, payload: dict, conversation: Conversation) -> list[dict]:
        messages_module = payload.get("modules", {}).get("MESSAGES_MODULE", {})
        messages = messages_module.get("messages") if isinstance(messages_module, dict) else None
        if not isinstance(messages, list):
            return []

        cards = []
        for card in messages:
            if not isinstance(card, dict) or card.get("_type") != "OfferMessageCard":
                continue
            parsed = self._parse_card(card, conversation)
            if parsed:
                cards.append(parsed)
        return sorted(cards, key=lambda item: item["sent_at"])

    def _upsert_offer_message(self, account: EbayAccount, conversation: Conversation, card: dict) -> Message:
        provider_message_id = card["provider_offer_id"]
        message = self.db.scalar(
            select(Message).where(
                Message.provider == "EBAY",
                Message.provider_message_id == provider_message_id,
            )
        )
        if not message:
            message = Message(
                provider="EBAY",
                provider_message_id=provider_message_id,
                conversation_id=conversation.id,
                sender_type=MessageSenderType.SYSTEM,
                sender_identifier=card["buyer_username"] if card["direction"] == OfferDirection.INCOMING else account.ebay_username,
                recipient_identifier=account.ebay_username if card["direction"] == OfferDirection.INCOMING else card["buyer_username"],
                body=card["label"],
                is_inbound=card["direction"] == OfferDirection.INCOMING,
                sent_at=card["sent_at"],
                raw_payload={"source": "ufe_conversation_offer_card", "card": card["raw"]},
                offer_data={"notification_type": "OFFER"},
            )
            self.db.add(message)
            self.db.flush()
        else:
            message.conversation_id = conversation.id
            message.sender_type = MessageSenderType.SYSTEM
            message.sender_identifier = card["buyer_username"] if card["direction"] == OfferDirection.INCOMING else account.ebay_username
            message.recipient_identifier = account.ebay_username if card["direction"] == OfferDirection.INCOMING else card["buyer_username"]
            message.body = card["label"]
            message.is_inbound = card["direction"] == OfferDirection.INCOMING
            message.sent_at = card["sent_at"]
            message.raw_payload = {"source": "ufe_conversation_offer_card", "card": card["raw"]}
            message.offer_data = {"notification_type": "OFFER"}
        return message

    def _parse_card(self, card: dict, conversation: Conversation) -> dict | None:
        amount, currency = self._amount(card)
        if amount is None:
            return None

        label = self._text(card.get("messageText")) or "Offer"
        direction = OfferDirection.OUTGOING if card.get("messageAlignment") == "RIGHT" else OfferDirection.INCOMING
        status = self._status(card, label)
        sent_at = self._datetime(self._nested(card, ("messagePostedTime", "value", "value"))) or datetime.now(UTC)
        provider_offer_id = f"ufe:{conversation.provider_conversation_id}:{card.get('messageId') or sent_at.isoformat()}"

        return {
            "provider_offer_id": provider_offer_id,
            "amount": amount,
            "currency": currency,
            "status": status,
            "direction": direction,
            "offer_type": self._offer_type(label, direction, status),
            "label": label,
            "sent_at": sent_at,
            "buyer_username": conversation.buyer_identifier,
            "raw": card,
        }

    def _amount(self, card: dict) -> tuple[Decimal | None, str]:
        value = self._nested(card, ("amount", "value"))
        value = value if isinstance(value, dict) else {}
        try:
            amount = Decimal(str(value.get("value")))
        except (InvalidOperation, TypeError):
            return None, "USD"
        return amount, str(value.get("currency") or "USD").upper()

    def _status(self, card: dict, label: str) -> str:
        lower = label.lower()
        if "accepted" in lower:
            return OfferStatus.ACCEPTED
        if "declined" in lower:
            return OfferStatus.DECLINED
        if "expired" in lower:
            return OfferStatus.EXPIRED
        return OfferStatus.PENDING

    def _offer_type(self, label: str, direction: str, status: str) -> str:
        lower = label.lower()
        if status == OfferStatus.ACCEPTED:
            return "ACCEPTED_OFFER"
        if "counteroffer" in lower:
            return "SELLER_COUNTEROFFER" if direction == OfferDirection.OUTGOING else "BUYER_COUNTEROFFER"
        return "SELLER_OFFER" if direction == OfferDirection.OUTGOING else "BUYER_OFFER"

    def _text(self, value: Any) -> str:
        if not isinstance(value, list):
            return ""
        parts = []
        for item in value:
            if not isinstance(item, dict):
                continue
            spans = item.get("textSpans")
            if isinstance(spans, list):
                parts.extend(str(span.get("text") or "") for span in spans if isinstance(span, dict))
        return " ".join(" ".join(parts).split())

    def _datetime(self, value: Any) -> datetime | None:
        if not isinstance(value, str) or not value.strip():
            return None
        normalized = value.strip()
        if normalized.endswith("Z"):
            normalized = f"{normalized[:-1]}+00:00"
        try:
            parsed = datetime.fromisoformat(normalized)
        except ValueError:
            return None
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)

    def _nested(self, payload: dict, keys: tuple[str, ...]) -> Any:
        current: Any = payload
        for key in keys:
            if not isinstance(current, dict):
                return None
            current = current.get(key)
        return current
