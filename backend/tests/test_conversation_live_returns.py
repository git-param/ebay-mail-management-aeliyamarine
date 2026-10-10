from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import Mock
from uuid import uuid4
from urllib.parse import parse_qs, urlsplit

import pytest
from fastapi import HTTPException, Response

from app.services import conversation_live_returns_service as live
from app.modules.integrations.ebay.client.ebay_auth_client import EbayAuthClient


def response(payload, status=200):
    return SimpleNamespace(ok=status == 200, status_code=status, payload=payload)


def setup(monkeypatch):
    account_id = uuid4()
    account = SimpleNamespace(id=account_id, is_active=True, environment='PRODUCTION',
                              access_token='seller-token', access_token_expires_at=datetime.now(UTC) + timedelta(hours=1))
    order = SimpleNamespace(id=uuid4(), account_id=account_id, buyer_username='buyer', order_id='order-123',
                            raw_payload={'lineItems': [{'listingMarketplaceId': 'EBAY_DE'}]})
    thread = SimpleNamespace(provider_account_id=account_id, buyer_identifier='Buyer')
    db = Mock()
    db.get.return_value = account
    service = live.ConversationLiveReturnsService(db)
    service.context = Mock()
    service.context.context_for_conversation.return_value = {'selected_order': order, 'candidate_orders': []}
    tokens = Mock()
    tokens.client.search_returns_raw.return_value = response({'members': []})
    monkeypatch.setattr(live, 'EbayTokenService', Mock(return_value=tokens))
    return service, thread, order, account, db, tokens


def test_fetches_live_summary_and_full_details_without_persisting(monkeypatch):
    service, thread, order, account, db, tokens = setup(monkeypatch)
    tokens.client.search_returns_raw.return_value = response({'members': [{
        'returnId': 'return-456', 'orderId': 'order-123', 'status': 'OPEN', 'state': 'ITEM_SHIPPED',
        'creationInfo': {'reason': 'DEFECTIVE', 'creationDate': {'value': '2026-10-10T10:00:00Z'}},
    }], 'paginationOutput': {'totalEntries': 11}})
    tokens.client.get_return_raw.return_value = response({'detail': {
        'refundInfo': {'actualRefundDetail': {'refundStatus': 'SUCCESS',
                       'actualRefund': {'totalAmount': {'value': 25, 'currency': 'USD'}}}},
        'returnShipmentInfo': {'shipmentTracking': {'carrierUsed': 'DHL', 'trackingNumber': 'tracking-123'}},
    }})
    result = service.fetch(thread)
    tokens.client.search_returns_raw.assert_called_once_with(
        'seller-token', order_id='order-123', marketplace_id='EBAY_DE', limit=10, offset=0,
    )
    tokens.client.get_return_raw.assert_called_once_with('seller-token', return_id='return-456', marketplace_id='EBAY_DE')
    assert result['next_offset'] == 10
    assert result['returns'][0]['return_id'] == 'return-456'
    sections = {section['title']: {row['label']: row['value'] for row in section['rows']}
                for section in result['returns'][0]['sections']}
    assert sections['Refund']['Refunded amount'] == '25 USD'
    assert sections['Refund']['Status'] == 'SUCCESS'
    assert sections['Return shipping 1']['Tracking number'] == 'tracking-123'
    assert result['returns'][0]['warning'] is None
    db.add.assert_not_called()
    db.commit.assert_not_called()
    service.context.select_order.assert_not_called()


def test_empty_results_are_valid_and_skip_detail_calls(monkeypatch):
    service, thread, _, _, db, tokens = setup(monkeypatch)
    result = service.fetch(thread)
    assert result['returns'] == []
    assert result['next_offset'] is None
    tokens.client.get_return_raw.assert_not_called()
    db.commit.assert_not_called()


@pytest.mark.parametrize('failure', [response({}, 403), HTTPException(502, 'timeout'), response({'unexpected': True})])
def test_detail_failure_keeps_live_summary_with_warning(monkeypatch, failure):
    service, thread, _, _, _, tokens = setup(monkeypatch)
    tokens.client.search_returns_raw.return_value = response({'members': [{'returnId': 'return-1', 'status': 'OPEN'}]})
    if isinstance(failure, Exception):
        tokens.client.get_return_raw.side_effect = failure
    else:
        tokens.client.get_return_raw.return_value = failure
    result = service.fetch(thread)
    assert result['returns'][0]['warning']
    assert result['returns'][0]['sections'][0]['rows'] == [{'label': 'Status', 'value': 'OPEN'}]


@pytest.mark.parametrize('invalid', ['account', 'buyer', 'missing-order', 'sandbox'])
def test_invalid_context_never_calls_ebay(monkeypatch, invalid):
    service, thread, order, account, _, tokens = setup(monkeypatch)
    if invalid == 'account': order.account_id = uuid4()
    if invalid == 'buyer': order.buyer_username = 'other'
    if invalid == 'missing-order': service.context.context_for_conversation.return_value['selected_order'] = None
    if invalid == 'sandbox': account.environment = 'SANDBOX'
    with pytest.raises(HTTPException): service.fetch(thread)
    tokens.client.search_returns_raw.assert_not_called()


def test_access_denied_is_not_an_empty_return_list(monkeypatch):
    service, thread, _, _, _, tokens = setup(monkeypatch)
    tokens.client.search_returns_raw.return_value = response({}, 403)
    with pytest.raises(HTTPException, match='Post-Order API access'):
        service.fetch(thread)


def test_expired_provider_token_is_refreshed_and_search_retried(monkeypatch):
    service, thread, _, account, _, tokens = setup(monkeypatch)
    tokens.client.search_returns_raw.side_effect = [response({}, 401), response({'members': []})]
    tokens.refresh_access_token.return_value = SimpleNamespace(access_token='fresh-token')
    assert service.fetch(thread)['returns'] == []
    tokens.refresh_access_token.assert_called_once_with(account.id)
    assert tokens.client.search_returns_raw.call_args_list[-1].args == ('fresh-token',)


def test_foreign_return_is_not_fetched(monkeypatch):
    service, thread, _, _, _, tokens = setup(monkeypatch)
    tokens.client.search_returns_raw.return_value = response({'members': [{'returnId': 'return-1', 'orderId': 'other-order'}]})
    assert service.fetch(thread)['returns'] == []
    tokens.client.get_return_raw.assert_not_called()


def test_post_order_request_headers_and_encoded_ids():
    client = EbayAuthClient(client_id='test', client_secret='test', redirect_uri='test', runame='test', environment='PRODUCTION')
    client._request_json_api_raw = Mock()
    client.search_returns_raw('secret-token', order_id='order/123', marketplace_id='EBAY_DE', offset=10)
    call = client._request_json_api_raw.call_args.kwargs
    assert call['extra_headers']['Authorization'] == 'IAF secret-token'
    assert call['extra_headers']['X-EBAY-C-MARKETPLACE-ID'] == 'EBAY_DE'
    assert parse_qs(urlsplit(call['request_url']).query)['order_id'] == ['order/123']
    assert parse_qs(urlsplit(call['request_url']).query)['offset'] == ['10']
    client.get_return_raw('secret-token', return_id='return/123', marketplace_id='EBAY_DE')
    assert '/return/return%2F123?fieldgroups=FULL' in client._request_json_api_raw.call_args.kwargs['request_url']
    assert client._sanitize_headers({'Authorization': 'IAF secret-token'})['Authorization'] == 'IAF ***'


def test_live_route_disables_caching_and_does_not_mark_read(monkeypatch):
    from app.api.v1.routes import conversations as routes
    conversations = Mock()
    service = Mock()
    service.fetch.return_value = {'order_id': 'order-123', 'returns': [], 'fetched_at': datetime.now(UTC)}
    monkeypatch.setattr(routes, 'ConversationService', Mock(return_value=conversations))
    monkeypatch.setattr(routes, 'ConversationLiveReturnsService', Mock(return_value=service))
    http_response = Response()
    db = Mock()
    routes.fetch_conversation_live_returns(uuid4(), http_response, offset=0, db=db, current_user=Mock())
    assert http_response.headers['Cache-Control'] == 'no-store'
    conversations.mark_read.assert_not_called()
    db.commit.assert_not_called()
