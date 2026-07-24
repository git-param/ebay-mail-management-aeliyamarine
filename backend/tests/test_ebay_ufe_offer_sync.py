from decimal import Decimal
from types import SimpleNamespace

from app.models.offer import OfferDirection, OfferStatus
from app.modules.integrations.ebay.services.ebay_ufe_offer_sync_service import EbayUfeOfferSyncService


def offer_card(message_id, label, amount, status, alignment, posted_at):
    return {
        "_type": "OfferMessageCard",
        "amount": {"value": {"value": amount, "currency": "USD"}},
        "status": status,
        "messageText": [{"textSpans": [{"text": label}]}],
        "messageId": message_id,
        "messageType": "OFFER",
        "messageAlignment": alignment,
        "messagePostedTime": {"value": {"value": posted_at}},
    }


def test_extracts_ufe_offer_cards_from_member_conversation_payload():
    service = EbayUfeOfferSyncService(db=None)
    conversation = SimpleNamespace(provider_conversation_id="126524602000", buyer_identifier="qfgm3292")
    payload = {
        "modules": {
            "MESSAGES_MODULE": {
                "messages": [
                    offer_card("274156627_3", "qfgm3292 accepted an offer", 100.06, "ACCEPTED", "LEFT", "2026-07-02T09:27:05.000Z"),
                    offer_card("274156627_2", "You sent a counteroffer", 100.06, "EXPIRED", "RIGHT", "2026-07-02T09:26:53.000Z"),
                    offer_card("274156582_1", "qfgm3292 sent an offer", 93, "COUNTERED", "LEFT", "2026-07-02T09:25:16.000Z"),
                ]
            }
        }
    }

    cards = service.extract_offer_cards(payload, conversation)

    assert [card["provider_offer_id"] for card in cards] == [
        "ufe:126524602000:274156582_1",
        "ufe:126524602000:274156627_2",
        "ufe:126524602000:274156627_3",
    ]
    assert cards[0]["amount"] == Decimal("93")
    assert cards[0]["direction"] == OfferDirection.INCOMING
    assert cards[0]["status"] == OfferStatus.PENDING
    assert cards[0]["offer_type"] == "BUYER_OFFER"
    assert cards[1]["direction"] == OfferDirection.OUTGOING
    assert cards[1]["status"] == OfferStatus.PENDING
    assert cards[1]["offer_type"] == "SELLER_COUNTEROFFER"
    assert cards[2]["status"] == OfferStatus.ACCEPTED
    assert cards[2]["offer_type"] == "ACCEPTED_OFFER"
