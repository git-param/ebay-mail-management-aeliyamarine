from datetime import UTC, datetime, timedelta
from decimal import Decimal
from types import SimpleNamespace
from uuid import uuid4
from urllib.error import URLError
import xml.etree.ElementTree as ET

import pytest
from fastapi import HTTPException
from pydantic import ValidationError

from app.api.dependencies import require_operations_manager_or_admin
from app.modules.integrations.ebay.client.ebay_auth_client import EbayAuthClient
from app.modules.integrations.ebay.schemas.best_offer_schemas import BestOfferActionRequest, BestOfferConfigUpdate
from app.modules.integrations.ebay.services.ebay_best_offer_query_service import actionable
from app.modules.integrations.ebay.services.ebay_offer_validation import update_missing_offer_fields
from app.services.ebay_best_offer_worker import dispatch
from app.services.ebay_best_offer_job_service import job_response
from app.modules.integrations.ebay.services.ebay_best_offer_status import status_group, status_label, reconciliation_delay


def client():
    return EbayAuthClient(client_id='test', client_secret='test', redirect_uri='test', runame='test', environment='PRODUCTION')


def test_notification_failure_identifies_provider_step_without_token(monkeypatch, caplog):
    from app.modules.integrations.ebay.services.ebay_offer_activity_service import EbayOfferActivityService
    service = object.__new__(EbayOfferActivityService)
    service.base = 'https://example.invalid'
    response = SimpleNamespace(ok=False, status_code=409,
        json=lambda: {'errors': [{'errorId': 195021, 'message': 'Destination exists for this endpoint. secret-token'}]})
    monkeypatch.setattr('app.modules.integrations.ebay.services.ebay_offer_activity_service.requests.request', lambda *args, **kwargs: response)
    with pytest.raises(HTTPException) as exc:
        service.request('POST', '/destination', 'secret-token')
    assert exc.value.status_code == 502
    assert 'POST /destination' in exc.value.detail
    assert '195021' in exc.value.detail
    assert 'secret-token' not in exc.value.detail
    assert 'secret-token' not in caplog.text


@pytest.mark.parametrize('hours,minutes', [(0,0),(0,1),(-1,5),(0,60),(168,1),(True,5)])
def test_invalid_interval(hours, minutes):
    with pytest.raises(ValidationError):
        BestOfferConfigUpdate(hours=hours, minutes=minutes)


def test_interval_requires_both_fields_and_accepts_five_minutes():
    with pytest.raises(ValidationError):
        BestOfferConfigUpdate(hours=1)
    assert BestOfferConfigUpdate(hours=0, minutes=5).minutes == 5


@pytest.mark.parametrize('changes', [{'amount':'0'}, {'quantity':0}, {'amount':'NaN'}, {'message':'x'*251}, {'quantity':1.5}])
def test_invalid_counter(changes):
    values = dict(action='Counter', amount='50.00', quantity=2, expected_version=1, idempotency_key=uuid4())
    with pytest.raises(ValidationError):
        BestOfferActionRequest(**{**values, **changes})


def offer(**changes):
    return SimpleNamespace(**{**dict(provider_offer_id='123', listing_id='456', record_source='TRADING',
        provider_role='Seller', provider_status='Active', reconciliation_required=False,
        expires_at=datetime.now(UTC)+timedelta(hours=1), provider_snapshot={
            'amount':'20', 'currency':'USD', 'quantity':2, 'offerType':'BuyerBestOffer'}), **changes})


@pytest.mark.parametrize('changes', [dict(record_source='MESSAGE_PARSE'),dict(record_source='DERIVED'),
    dict(provider_role=None),dict(provider_role='Buyer'),dict(provider_status='SellerAccept'),
    dict(provider_status='Accepted'),dict(reconciliation_required=True),dict(provider_offer_id='123:seller-counteroffer-submitted'),
    dict(expires_at=datetime.now(UTC)-timedelta(seconds=1)),dict(provider_snapshot={'amount':'20','quantity':1,'offerType':'BuyerBestOffer'})])
def test_non_actionable_evidence(changes):
    assert not actionable(offer(**changes))


def test_pending_action_blocks_duplicates():
    assert actionable(offer())
    assert not actionable(offer(), SimpleNamespace(state='DISPATCHING'))
    assert not actionable(offer(), SimpleNamespace(state='RECONCILIATION_REQUIRED'))
    assert not actionable(offer(), SimpleNamespace(state='SUCCEEDED'))


def test_message_parse_cannot_replace_trading_status():
    record = offer()
    record.status = 'ACCEPTED'
    update_missing_offer_fields(record, {'status':'PENDING', 'raw_payload':{'source':'on_demand_message_parse'}})
    assert record.status == 'ACCEPTED'
    assert record.record_source == 'TRADING'


def test_agent_cannot_manage_config():
    with pytest.raises(HTTPException) as exc:
        require_operations_manager_or_admin(SimpleNamespace(role=SimpleNamespace(name='AGENT')))
    assert exc.value.status_code == 403
    for role in ['Admin','Operations Manager','Ops Manager']:
        user = SimpleNamespace(role=SimpleNamespace(name=role))
        assert require_operations_manager_or_admin(user) is user


def test_dispatch_existing_reservation_never_spawns(monkeypatch):
    monkeypatch.setattr('app.services.ebay_best_offer_worker.multiprocessing.get_context', lambda *_: pytest.fail('Duplicate spawn'))
    assert dispatch({'newly_reserved':False}) == {'newly_reserved':False}


@pytest.mark.parametrize('xml,confirmed,ambiguous', [
    ('<Ack>Success</Ack>',False,True),
    ('<Ack>Success</Ack><RespondToBestOffer><BestOffer><CallStatus>Success</CallStatus></BestOffer></RespondToBestOffer>',True,False),
    ('<Ack>Warning</Ack><RespondToBestOffer><BestOffer><CallStatus>Success</CallStatus></BestOffer></RespondToBestOffer>',True,False),
    ('<Ack>Failure</Ack><Errors><ErrorCode>219</ErrorCode><SeverityCode>Error</SeverityCode></Errors>',False,False),
    ('<Ack>Success</Ack><RespondToBestOffer><BestOffer><CallStatus>Failure</CallStatus></BestOffer></RespondToBestOffer>',False,False)])
def test_response_requires_operation_confirmation(xml, confirmed, ambiguous):
    result = client()._best_offer_action_xml('<RespondToBestOfferResponse xmlns="urn:ebay:apis:eBLBaseComponents">'+xml+'</RespondToBestOfferResponse>')
    assert result['confirmed'] is confirmed
    assert result['ambiguous'] is ambiguous


def test_malformed_reply_is_ambiguous():
    assert client()._best_offer_action_xml('<broken')['ambiguous']


def test_counter_total_and_xml_escaping_single_attempt(monkeypatch):
    requests = []
    def network(request, **_):
        requests.append(request)
        raise URLError('timeout')
    monkeypatch.setattr('app.modules.integrations.ebay.client.ebay_auth_client.urlopen', network)
    result = client().respond_to_best_offer_raw('secret', action='Counter', offer_id='123', item_id='456',
        amount=Decimal('60.00'), currency='USD', quantity=3, message='A & B < C')
    assert result.payload['ambiguous']
    assert len(requests) == 1
    xml = ET.fromstring(requests[0].data)
    ns = {'e':'urn:ebay:apis:eBLBaseComponents'}
    assert xml.findtext('e:CounterOfferPrice', namespaces=ns) == '60.00'
    assert xml.findtext('e:CounterOfferQuantity', namespaces=ns) == '3'
    assert xml.findtext('e:SellerResponse', namespaces=ns) == 'A & B < C'
    assert 'secret' not in str(result.request_headers)


def test_grouped_role_and_missing_values_preserved():
    xml = '''<GetBestOffersResponse xmlns="urn:ebay:apis:eBLBaseComponents"><Ack>Success</Ack>
    <ItemBestOffersArray><ItemBestOffers><Role>Seller</Role><Item><ItemID>456</ItemID></Item>
    <BestOfferArray><BestOffer><BestOfferID>123</BestOfferID><Status>FutureProviderState</Status>
    <BestOfferCodeType>BuyerBestOffer</BestOfferCodeType></BestOffer></BestOfferArray></ItemBestOffers></ItemBestOffersArray>
    <PaginationResult><TotalNumberOfPages>3</TotalNumberOfPages></PaginationResult></GetBestOffersResponse>'''
    result = client()._best_offers_xml(xml)
    assert result['totalPages'] == 3
    assert result['offers'][0]['role'] == 'Seller'
    assert result['offers'][0]['status'] == 'FutureProviderState'
    assert result['offers'][0]['quantity'] is None
    assert result['offers'][0]['offerType'] == 'BuyerBestOffer'


def test_all_requires_listing_without_outbound(monkeypatch):
    monkeypatch.setattr('app.modules.integrations.ebay.client.ebay_auth_client.urlopen', lambda *_: pytest.fail('Unexpected call'))
    with pytest.raises(ValueError):
        client().get_best_offers_raw('secret', best_offer_status='All')


@pytest.mark.parametrize('shape', ['grouped', 'flat'])
def test_parser_keeps_role_listing_price_and_exact_transitional_status_in_both_shapes(shape):
    body = '''<Role>Seller</Role><Item><ItemID>456</ItemID><Title>Test item</Title>
    <BuyItNowPrice currencyID="EUR">100</BuyItNowPrice></Item><BestOfferArray><BestOffer>
    <BestOfferID>123</BestOfferID><Price currencyID="EUR">80</Price><Quantity>1</Quantity>
    <Status>PendingBuyerPayment</Status></BestOffer></BestOfferArray>'''
    if shape == 'grouped':
        body = '<ItemBestOffersArray><ItemBestOffers>' + body + '</ItemBestOffers></ItemBestOffersArray>'
    parsed = client()._best_offers_xml('<GetBestOffersResponse xmlns="urn:ebay:apis:eBLBaseComponents"><Ack>Success</Ack>' + body + '</GetBestOffersResponse>')['offers'][0]
    assert parsed['role'] == 'Seller' and parsed['listingId'] == '456'
    assert parsed['listing'] == {'price': '100', 'currency': 'EUR', 'title': 'Test item'}
    assert parsed['status'] == 'PendingBuyerPayment' and parsed['currency'] == 'EUR'


def test_parser_does_not_infer_role_from_offer_type_or_buyer():
    parsed = client()._best_offers_xml('''<GetBestOffersResponse xmlns="urn:ebay:apis:eBLBaseComponents">
    <Ack>Success</Ack><BestOfferArray><BestOffer><BestOfferID>123</BestOfferID>
    <Buyer><UserID>buyer</UserID></Buyer><BestOfferCodeType>BuyerBestOffer</BestOfferCodeType>
    <Status>FutureProviderState</Status></BestOffer></BestOfferArray></GetBestOffersResponse>''')['offers'][0]
    assert parsed['role'] is None
    assert parsed['status'] == 'FutureProviderState'


@pytest.mark.parametrize('state,group,minutes', [
    ('Active', 'OPEN', 5), ('Countered', 'OPEN', 5), ('SellerAccept', 'AGREED', 5),
    ('PendingBuyerConfirmation', 'AGREED', 5), ('PendingBuyerPayment', 'AGREED', 15),
    ('Accepted', 'COMPLETED', 10080), ('AdminEnded', 'CLOSED', 10080),
    ('Expired', 'CLOSED', 10080), ('FutureProviderState', 'UNKNOWN', 60),
])
def test_lifecycle_and_polling_preserve_provider_states(state, group, minutes):
    assert status_group(state) == group
    assert reconciliation_delay([state], returned=1) == timedelta(minutes=minutes)
    assert status_label('FutureProviderState') == 'FutureProviderState'


def test_unresolved_actions_override_closed_backoff_and_empty_listings_wait():
    assert reconciliation_delay(['Accepted'], unresolved=True, returned=1) == timedelta(minutes=5)
    assert reconciliation_delay([], returned=0) == timedelta(hours=12)
    assert reconciliation_delay(['PendingBuyerPayment', 'Active'], returned=2) == timedelta(minutes=5)


def test_job_response_reports_separate_discovery_reconciliation_and_change_counts():
    metadata = {'discovery': {'returned': 14}, 'reconciliation': {'reconciled': 22},
        'changes': {'new': 3, 'updated': 7, 'status_changes': 6, 'unchanged': 27}, 'api_calls': 24}
    job = SimpleNamespace(id=uuid4(), provider_account_id=uuid4(), status=SimpleNamespace(value='SUCCESS'),
        started_at=None, completed_at=None, records_processed=10, error_message=None, sync_metadata=metadata)
    statistics = job_response(job)['result']['statistics']
    assert statistics == {'active_discovered': 14, 'listings_reconciled': 22, 'new_offers': 3,
        'status_changes': 6, 'updated_offers': 7, 'unchanged': 27, 'api_calls': 24}
    assert 'statistics' not in metadata


def test_token_refresh_preserves_original_grant_in_one_request(monkeypatch):
    from urllib.parse import parse_qs
    import app.modules.integrations.ebay.client.ebay_auth_client as auth
    requests = []
    class Response:
        def __enter__(self):
            return self
        def __exit__(self, *_args):
            pass
        def read(self):
            return b'{"access_token":"test-access","expires_in":7200}'
    def request(req, **_kwargs):
        requests.append(parse_qs(req.data.decode()))
        return Response()
    monkeypatch.setattr(auth, 'urlopen', request)
    result = client().refresh_access_token('test-refresh')
    assert result.access_token == 'test-access'
    assert requests == [{'grant_type':['refresh_token'], 'refresh_token':['test-refresh']}]


@pytest.mark.parametrize('error', ['invalid_grant', 'invalid_client', 'invalid_scope'])
def test_token_refresh_does_not_retry_failed_grants(monkeypatch, error):
    import io
    from urllib.error import HTTPError
    import app.modules.integrations.ebay.client.ebay_auth_client as auth
    calls = []
    def request(req, **_kwargs):
        calls.append(req)
        raise HTTPError(req.full_url, 400, 'Bad Request', {}, io.BytesIO(
            ('{"error":"'+error+'","error_description":"Test rejection"}').encode()))
    monkeypatch.setattr(auth, 'urlopen', request)
    with pytest.raises(HTTPException):
        client().refresh_access_token('test-refresh')
    assert len(calls) == 1


def test_offer_activity_consent_is_explicit_and_does_not_change_normal_connect():
    from urllib.parse import urlparse, parse_qs
    regular = parse_qs(urlparse(client().build_authorization_url(state='state')).query)['scope'][0]
    offers = parse_qs(urlparse(client().build_authorization_url(state='state', offer_activity=True)).query)['scope'][0]
    assert '/sell.offer' not in regular and '/buy.offer' not in regular
    assert '/sell.offer' in offers and '/commerce.notification.subscription' in offers
    assert '/buy.offer' not in offers


def test_offer_notification_signature_rejects_tampered_payload():
    import base64, json
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import ec
    from app.modules.integrations.ebay.services.ebay_offer_activity_service import verify_signature
    key = ec.generate_private_key(ec.SECP256R1())
    body = b'{"notification":{"data":{"itemId":"123"}}}'
    signature = key.sign(body, ec.ECDSA(hashes.SHA1()))
    header = base64.b64encode(json.dumps({'kid':'test-key', 'signature':base64.b64encode(signature).decode()}).encode()).decode()
    public_key = key.public_key().public_bytes(serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo).decode()
    verify_signature(body, header, public_key)
    with pytest.raises(HTTPException) as error:
        verify_signature(body.replace(b'123', b'456'), header, public_key)
    assert error.value.status_code == 412
