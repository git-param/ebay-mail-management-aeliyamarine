import unittest
from datetime import UTC, datetime

from app.modules.integrations.ebay.client.ebay_auth_client import EBAY_OAUTH_SCOPES, EbayRawApiResponse
from app.modules.integrations.ebay.orders.providers import FulfillmentOrderProvider
from app.modules.integrations.ebay.services.ebay_order_sync_service import EbayOrderSyncService


class FakeOrderClient:
    def __init__(self, payload):
        self.payload = payload
        self.calls = []

    def get_orders_raw(self, access_token, **kwargs):
        self.calls.append((access_token, kwargs))
        return EbayRawApiResponse(200, self.payload, True, 'https://example.test/orders', {})


class FulfillmentOrderProviderTests(unittest.TestCase):
    def test_oauth_requests_fulfillment_without_removing_existing_scopes(self):
        self.assertIn('https://api.ebay.com/oauth/api_scope/sell.fulfillment', EBAY_OAUTH_SCOPES)
        self.assertIn('https://api.ebay.com/oauth/api_scope/commerce.message', EBAY_OAUTH_SCOPES)
        self.assertIn('https://api.ebay.com/oauth/api_scope/sell.inventory', EBAY_OAUTH_SCOPES)

    def test_page_parsing_uses_next_link_for_pagination(self):
        client = FakeOrderClient({'orders': [{'orderId': '1'}], 'total': 2, 'next': '/orders?offset=1'})
        provider = FulfillmentOrderProvider(client)

        page = provider.fetch_page('token', limit=200, offset=0, filter_value='filter')

        self.assertEqual([{'orderId': '1'}], page.orders)
        self.assertEqual(2, page.total)
        self.assertTrue(page.has_more)
        self.assertEqual('filter', client.calls[0][1]['filter_value'])

    def test_incremental_filter_uses_last_modified_date(self):
        service = object.__new__(EbayOrderSyncService)
        cursor = datetime(2026, 6, 29, 10, 0, tzinfo=UTC)
        end = datetime(2026, 6, 29, 11, 0, tzinfo=UTC)

        value = service._incremental_filter(cursor, end)

        self.assertEqual(
            'lastmodifieddate:[2026-06-29T09:55:00.000Z..2026-06-29T11:00:00.000Z]',
            value,
        )

    def test_first_sync_has_no_filter(self):
        service = object.__new__(EbayOrderSyncService)
        self.assertIsNone(service._incremental_filter(None, datetime.now(UTC)))


if __name__ == '__main__':
    unittest.main()
