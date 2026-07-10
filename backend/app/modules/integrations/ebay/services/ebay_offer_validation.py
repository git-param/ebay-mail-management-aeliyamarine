import logging
from typing import Any

from app.models.offer import OfferDirection, OfferStatus


SYSTEM_SENDERS = {"ebay", "from ebay", "system", "ebay system"}
SELLER_DIRECTION_VALUES = {"OUTGOING", "SELLER_TO_BUYER"}
BUYER_DIRECTION_VALUES = {"INCOMING", "BUYER_TO_SELLER"}
SYSTEM_DIRECTION_VALUES = {"SYSTEM"}
OFFER_UPDATE_FIELDS = (
    "listing_id",
    "buyer_username",
    "offer_amount",
    "currency",
    "status",
    "direction",
    "offer_type",
    "quantity",
    "raw_text",
    "raw_payload",
    "expires_at",
    "created_at_provider",
)
OFFER_ALWAYS_UPDATE_FIELDS = {
    "offer_amount",
    "status",
    "direction",
    "offer_type",
    "quantity",
    "expires_at",
    "raw_payload",
}


def infer_offer_direction(message: Any = None, account: Any = None) -> str | None:
    raw_payload = getattr(message, "raw_payload", None)
    raw_payload = raw_payload if isinstance(raw_payload, dict) else {}
    sender = raw_payload.get("senderUsername") or getattr(message, "sender_identifier", None)
    account_username = getattr(account, "ebay_username", None)

    if not sender:
        return None

    sender_normalized = str(sender).strip().lower()
    if sender_normalized in SYSTEM_SENDERS:
        return "SYSTEM"

    if account_username and sender_normalized == str(account_username).strip().lower():
        return OfferDirection.OUTGOING

    return OfferDirection.INCOMING


def normalize_offer_direction(value: Any) -> str | None:
    if value is None:
        return None
    normalized = str(value).strip().upper()
    if normalized in SELLER_DIRECTION_VALUES:
        return OfferDirection.OUTGOING
    if normalized in BUYER_DIRECTION_VALUES:
        return OfferDirection.INCOMING
    if normalized in SYSTEM_DIRECTION_VALUES:
        return "SYSTEM"
    return None


def normalize_extracted_offer(
    extracted_offer: dict | None,
    *,
    message: Any = None,
    account: Any = None,
    logger: logging.Logger | None = None,
) -> tuple[dict | None, str | None]:
    if not extracted_offer:
        return None, "empty_extracted_offer"

    provider_offer_id = extracted_offer.get("provider_offer_id")
    if not provider_offer_id:
        return None, "missing_provider_offer_id"

    direction = normalize_offer_direction(extracted_offer.get("direction"))
    if not direction:
        direction = infer_offer_direction(message, account)

    if not direction:
        return None, "missing_direction"

    normalized = dict(extracted_offer)
    normalized["provider_offer_id"] = str(provider_offer_id).strip()
    normalized["direction"] = direction
    normalized["currency"] = normalized.get("currency") or "USD"
    normalized["status"] = normalized.get("status") or OfferStatus.PENDING
    normalized["quantity"] = normalized.get("quantity") or 1

    if logger:
        logger.debug(
            "Normalized extracted eBay offer provider_offer_id=%s direction=%s",
            normalized["provider_offer_id"],
            normalized["direction"],
        )

    return normalized, None


def update_missing_offer_fields(
    offer: Any,
    offer_data: dict,
    fields: tuple[str, ...] = OFFER_UPDATE_FIELDS,
) -> None:
    for field in fields:
        value = offer_data.get(field)
        if value is None:
            continue
        if field in OFFER_ALWAYS_UPDATE_FIELDS:
            setattr(offer, field, value)
        elif getattr(offer, field, None) in (None, ""):
            setattr(offer, field, value)
