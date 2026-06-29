import unittest
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import MagicMock, patch
from uuid import uuid4

from app.models.conversation import Conversation
from app.models.order_context import ConversationProductContext
from app.services.conversation_product_context_service import BrowseApiError, ConversationProductContextService


class ConversationProductContextServiceTests(unittest.TestCase):
    def setUp(self):
        self.service = object.__new__(ConversationProductContextService)
        self.service.db = MagicMock()
        self.service.settings = SimpleNamespace(
            ebay_environment='PRODUCTION',
            ebay_marketplace_id='EBAY_US',
            ebay_browse_max_retries=3,
            ebay_browse_retry_base_seconds=0,
        )
        self.service._app_token = 'token'
        self.service._app_token_expires_at = datetime.now(UTC)
        self.service._app_token_environment = 'PRODUCTION'
        self.service._reference_cache = {}
        self.service._environment = MagicMock(return_value='PRODUCTION')
        self.service._find_cached_context = MagicMock(return_value=None)
        self.service._enrich_from_local_order = MagicMock(return_value=False)

    def _conversation_and_context(self, reference_id='123'):
        conversation = Conversation(
            id=uuid4(), provider='EBAY', provider_conversation_id=str(uuid4()),
            provider_account_id=uuid4(), reference_id=reference_id, reference_type='LISTING',
        )
        context = ConversationProductContext(
            id=uuid4(), conversation_id=conversation.id, reference_id=reference_id,
            reference_type='LISTING', enrichment_status='PENDING',
        )
        return conversation, context

    def test_11001_is_terminal_and_non_fatal(self):
        conversation, context = self._conversation_and_context()
        self.service.get_context = MagicMock(return_value=context)
        self.service._get_item_by_legacy_id = MagicMock(
            side_effect=BrowseApiError(404, 11001, 'The specified item Id was not found.', {'errors': []})
        )
        result = self.service.enrich_conversation(conversation)
        self.assertEqual('UNAVAILABLE', result.enrichment_status)
        self.assertEqual(11001, result.raw_payload['error']['error_id'])

    def test_11003_terminal_result_is_cached(self):
        conversation, context = self._conversation_and_context()
        self.service.get_context = MagicMock(return_value=context)
        browse = MagicMock(
            side_effect=BrowseApiError(404, 11003, 'The specified legacy item Id was not found.', {'errors': []})
        )
        self.service._get_item_by_legacy_id = browse
        self.service.enrich_conversation(conversation)
        self.service.enrich_conversation(conversation)
        self.assertEqual('UNAVAILABLE', context.enrichment_status)
        browse.assert_called_once()

    def test_duplicate_reference_reuses_in_memory_result(self):
        first_conversation, first_context = self._conversation_and_context('456')
        second_conversation, second_context = self._conversation_and_context('456')
        contexts = {first_conversation.id: first_context, second_conversation.id: second_context}
        self.service.get_context = MagicMock(side_effect=lambda conversation_id: contexts[conversation_id])
        self.service._cache_key = MagicMock(return_value=('account', 'PRODUCTION', '456'))
        browse = MagicMock(return_value={'title': 'Cached title', 'image': {}, 'seller': {}})
        self.service._get_item_by_legacy_id = browse
        self.service.enrich_conversation(first_conversation)
        result = self.service.enrich_conversation(second_conversation)
        self.assertEqual('Cached title', result.item_title)
        self.assertEqual('ENRICHED', result.enrichment_status)
        browse.assert_called_once()

    def test_local_order_line_enrichment_skips_browse(self):
        conversation, context = self._conversation_and_context()
        self.service.get_context = MagicMock(return_value=context)

        def enrich_local(_conversation, target):
            target.item_title, target.sku, target.order_id = 'Local title', 'SKU-1', 'ORDER-1'
            return True

        self.service._enrich_from_local_order = MagicMock(side_effect=enrich_local)
        self.service._get_item_by_legacy_id = MagicMock()
        result = self.service.enrich_conversation(conversation)
        self.assertEqual('LOCAL_ORDER', result.enrichment_status)
        self.assertEqual('SKU-1', result.sku)
        self.service._get_item_by_legacy_id.assert_not_called()

    def test_401_clears_token_and_retries_once(self):
        self.service._request_item_by_legacy_id = MagicMock(
            side_effect=[BrowseApiError(401, None, 'Unauthorized'), {'title': 'ok'}]
        )
        payload = self.service._get_item_by_legacy_id('123', environment='PRODUCTION')
        self.assertEqual({'title': 'ok'}, payload)
        self.assertIsNone(self.service._app_token)
        self.assertEqual(2, self.service._request_item_by_legacy_id.call_count)

    @patch('app.services.conversation_product_context_service.sleep')
    def test_transient_failures_use_bounded_retries(self, sleep_mock):
        self.service._request_item_by_legacy_id = MagicMock(side_effect=[
            BrowseApiError(500, None, 'Server error', transient=True),
            BrowseApiError(429, None, 'Rate limited', transient=True),
            {'title': 'ok'},
        ])
        payload = self.service._get_item_by_legacy_id('123', environment='PRODUCTION')
        self.assertEqual({'title': 'ok'}, payload)
        self.assertEqual(3, self.service._request_item_by_legacy_id.call_count)
        self.assertEqual(2, sleep_mock.call_count)


if __name__ == '__main__':
    unittest.main()
