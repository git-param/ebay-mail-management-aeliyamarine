from decimal import Decimal

from app.modules.integrations.ebay.services.ebay_seller_offer_sync_service import EbaySellerOfferSyncService


def test_seller_offer_parser_extracts_buyer_sent_new_offer_subject():
    service = EbaySellerOfferSyncService(db=None)

    parsed = service._parse_offer_from_subject(
        "Buyer sent a new offer: EUR 85.00 for Vossloh z 1000 s Leu... (127896160216)"
    )

    assert parsed["amount"] == Decimal("85.00")
    assert parsed["currency"] == "EUR"
    assert parsed["direction"] == "INCOMING"
    assert parsed["offer_type"] == "BUYER_OFFER"
    assert parsed["item_id"] == "127896160216"
    assert "buyer" not in parsed


def test_seller_offer_parser_extracts_au_dollar_counteroffer_amount():
    service = EbaySellerOfferSyncService(db=None)

    parsed = service._parse_offer_from_subject(
        "Counteroffer submitted to buyer: AU $173.39 for Enraf 34382 Maintenance Repair Kit (406358458381)"
    )

    assert parsed["amount"] == Decimal("173.39")
    assert parsed["currency"] == "AUD"
    assert parsed["direction"] == "OUTGOING"
    assert parsed["offer_type"] == "SELLER_COUNTEROFFER"
    assert parsed["item_id"] == "406358458381"
    assert "buyer" not in parsed
