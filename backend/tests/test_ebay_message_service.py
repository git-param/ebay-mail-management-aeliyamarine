from app.modules.integrations.ebay.services.ebay_message_service import EbayMessageService


def test_is_inbound_message_prefers_buyer_sender():
    service = EbayMessageService.__new__(EbayMessageService)

    assert service._is_inbound_message(
        sender_normalized='n_ma067',
        recipient_normalized='aeliya110',
        seller_username='aeliya110',
        buyer_normalized='n_ma067',
    )


def test_is_inbound_message_uses_buyer_recipient_for_seller_message():
    service = EbayMessageService.__new__(EbayMessageService)

    assert not service._is_inbound_message(
        sender_normalized='aeliya110',
        recipient_normalized='n_ma067',
        seller_username='',
        buyer_normalized='n_ma067',
    )
