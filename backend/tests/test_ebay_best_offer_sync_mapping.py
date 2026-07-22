from app.models.offer import OfferDirection, OfferStatus
from app.modules.integrations.ebay.services.ebay_best_offer_sync_service import EbayBestOfferSyncService


def test_best_offer_sync_maps_trading_offer_types():
    service = EbayBestOfferSyncService(db=None)

    assert service._direction("BuyerBestOffer") == OfferDirection.INCOMING
    assert service._offer_type("BuyerBestOffer") == "BUYER_OFFER"
    assert service._direction("SellerCounterOffer") == OfferDirection.OUTGOING
    assert service._offer_type("SellerCounterOffer") == "SELLER_COUNTEROFFER"
    assert service._direction("BuyerCounterOffer") == OfferDirection.INCOMING
    assert service._offer_type("BuyerCounterOffer") == "BUYER_COUNTEROFFER"
    assert service._direction("SellerCounterOffer", "Accepted") == OfferDirection.INCOMING


def test_best_offer_sync_maps_all_relevant_statuses():
    service = EbayBestOfferSyncService(db=None)

    assert service._status("Active") == OfferStatus.PENDING
    assert service._status("Countered") == OfferStatus.COUNTERED
    assert service._status("Accepted") == OfferStatus.ACCEPTED
    assert service._status("Declined") == OfferStatus.DECLINED
    assert service._status("Expired") == OfferStatus.EXPIRED
    assert service._status("Withdrawn") == OfferStatus.RETRACTED
    assert service._status("Retracted") == OfferStatus.RETRACTED
