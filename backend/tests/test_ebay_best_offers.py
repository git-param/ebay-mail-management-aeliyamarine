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


def client():
    return EbayAuthClient(client_id='test', client_secret='test', redirect_uri='test', runame='test', environment='PRODUCTION')


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
