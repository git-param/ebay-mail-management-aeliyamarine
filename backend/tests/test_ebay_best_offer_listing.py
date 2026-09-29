from app.modules.integrations.ebay.services.ebay_best_offer_listing import merge_listing_metadata
from app.modules.integrations.ebay.client.ebay_auth_client import EbayAuthClient


def test_empty_provider_fields_keep_cached_preview_and_zero_price():
    listing = merge_listing_metadata(
        {'title': 'Cached title', 'image_url': 'https://example.invalid/cached.jpg', 'price': 20},
        {'title': ' ', 'image_url': None, 'price': 0})
    assert listing['title'] == 'Cached title'
    assert listing['image_url'] == 'https://example.invalid/cached.jpg'
    assert listing['price'] == 0


def test_latest_image_is_primary_and_cached_alternates_remain_available():
    listing = merge_listing_metadata(
        {'image_url': 'cached.jpg', 'image_urls': ['cached.jpg', 'alternate.jpg']},
        {'image_url': 'provider.jpg', 'image_urls': ['provider.jpg']})
    assert listing['image_url'] == 'provider.jpg'
    assert listing['image_urls'] == ['provider.jpg', 'cached.jpg', 'alternate.jpg']


def test_trading_parser_preserves_picture_and_gallery_previews():
    client = EbayAuthClient(client_id='test', client_secret='test', redirect_uri='test', runame='test', environment='PRODUCTION')
    result = client._best_offers_xml('''<GetBestOffersResponse xmlns="urn:ebay:apis:eBLBaseComponents">
    <Ack>Success</Ack><ItemBestOffersArray><ItemBestOffers><Item><ItemID>456</ItemID>
    <PictureDetails><PictureURL>https://example.invalid/one.jpg</PictureURL>
    <PictureURL>https://example.invalid/two.jpg</PictureURL>
    <GalleryURL>https://example.invalid/gallery.jpg</GalleryURL></PictureDetails></Item>
    <BestOfferArray><BestOffer><BestOfferID>123</BestOfferID></BestOffer></BestOfferArray>
    </ItemBestOffers></ItemBestOffersArray></GetBestOffersResponse>''')
    listing = result['offers'][0]['listing']
    assert listing['image_url'] == 'https://example.invalid/one.jpg'
    assert listing['image_urls'] == ['https://example.invalid/one.jpg', 'https://example.invalid/two.jpg', 'https://example.invalid/gallery.jpg']
