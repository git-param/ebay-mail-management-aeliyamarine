from types import SimpleNamespace
from decimal import Decimal

from app.modules.integrations.ebay.services.ebay_offer_validation import (
    infer_offer_direction,
    normalize_extracted_offer,
    update_missing_offer_fields,
)
from app.modules.integrations.ebay.services.ebay_conversation_offer_resolver import EbayConversationOfferResolver
from app.modules.integrations.ebay.services.ebay_seller_offer_sync_service import EbaySellerOfferSyncService


def test_normalize_extracted_offer_skips_missing_provider_offer_id():
    normalized, reason = normalize_extracted_offer({"direction": "INCOMING"})

    assert normalized is None
    assert reason == "missing_provider_offer_id"


def test_normalize_extracted_offer_infers_direction_and_defaults_required_values():
    message = SimpleNamespace(sender_identifier="buyer-1", raw_payload={})
    account = SimpleNamespace(ebay_username="seller-1")

    normalized, reason = normalize_extracted_offer(
        {"provider_offer_id": 123},
        message=message,
        account=account,
    )

    assert reason is None
    assert normalized["provider_offer_id"] == "123"
    assert normalized["direction"] == "INCOMING"
    assert normalized["currency"] == "USD"
    assert normalized["status"] == "PENDING"
    assert normalized["quantity"] == 1


def test_normalize_extracted_offer_skips_when_direction_cannot_be_inferred():
    message = SimpleNamespace(sender_identifier=None, raw_payload={})
    account = SimpleNamespace(ebay_username="seller-1")

    normalized, reason = normalize_extracted_offer(
        {"provider_offer_id": "offer-1", "direction": None},
        message=message,
        account=account,
    )

    assert normalized is None
    assert reason == "missing_direction"


def test_infer_offer_direction_uses_sender_context():
    account = SimpleNamespace(ebay_username="seller-1")

    assert infer_offer_direction(SimpleNamespace(sender_identifier="seller-1"), account) == "OUTGOING"
    assert infer_offer_direction(SimpleNamespace(sender_identifier="buyer-1"), account) == "INCOMING"
    assert infer_offer_direction(SimpleNamespace(sender_identifier="eBay"), account) == "SYSTEM"


def test_conversation_offer_resolver_reads_buyer_direction_from_notification_text():
    resolver = EbayConversationOfferResolver(db=None)
    message = SimpleNamespace(is_inbound=False)

    assert resolver._direction("buyer sent an offer usd 93.00", message) == "INCOMING"
    assert resolver._direction("you have a new offer usd 93.00", message) == "INCOMING"
    assert resolver._direction("you sent a counteroffer usd 100.06", message) == "OUTGOING"


def test_update_missing_offer_fields_corrects_existing_direction():
    offer = SimpleNamespace(direction="OUTGOING", currency="USD")

    update_missing_offer_fields(offer, {"direction": "INCOMING", "currency": "EUR"})

    assert offer.direction == "INCOMING"
    assert offer.currency == "USD"


def test_seller_offer_parser_does_not_treat_item_numbers_as_amounts():
    service = EbaySellerOfferSyncService(db=None)

    parsed = service._parse_offer_from_subject(
        "obsolete-spares555 accepted an offer for MERLIN GERIN C60HC C16 2 Pole Circuit Breaker 415V 16A (336157359770)"
    )

    assert parsed is not None
    assert parsed["status"] == "ACCEPTED"
    assert "amount" not in parsed
    assert parsed["item_id"] == "336157359770"


def test_seller_offer_parser_extracts_aud_offer_amount():
    service = EbaySellerOfferSyncService(db=None)

    parsed = service._parse_offer_from_subject(
        "Counteroffer submitted to buyer: AUD $173.39 for Enraf 34382 Maintenance Repair Kit (406358458381)"
    )

    assert parsed["amount"] == Decimal("173.39")
    assert parsed["currency"] == "AUD"
    assert parsed["direction"] == "OUTGOING"
    assert parsed["item_id"] == "406358458381"
    assert "buyer" not in parsed


def test_seller_offer_parser_extracts_au_dollar_counteroffer_amount():
    service = EbaySellerOfferSyncService(db=None)

    parsed = service._parse_offer_from_subject(
        "Counteroffer submitted to buyer: AU $173.39 for Enraf 34382 Maintenance Repair Kit (406358458381)"
    )

    assert parsed["amount"] == Decimal("173.39")
    assert parsed["currency"] == "AUD"
    assert parsed["direction"] == "OUTGOING"
    assert "buyer" not in parsed
