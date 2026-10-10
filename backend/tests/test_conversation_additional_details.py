from types import SimpleNamespace
from datetime import UTC, datetime
from unittest.mock import Mock
from uuid import uuid4

from app.services.conversation_additional_details_service import (
    ConversationAdditionalDetailsService, extract_order_details,
)


def order(payload=None, **overrides):
    return SimpleNamespace(
        raw_payload=payload, order_id='05-15004-65409', payment_status=None,
        fulfillment_status=None, cancel_status=None, pricing_summary=None,
        **overrides,
    )


def test_extracts_contacts_shipping_payment_dates_and_zero_cost_without_mutating_payload():
    payload = {
        'buyer': {'buyerRegistrationAddress': {
            'fullName': 'Buyer name', 'email': 'buyer@members.ebay.com',
            'contactAddress': {'postalCode': '186302', 'city': 'Sharjah'},
        }},
        'orderPaymentStatus': 'PAID',
        'cancelStatus': {'cancelState': 'NONE_REQUESTED'},
        'fulfillmentStartInstructions': [{'shippingStep': {
            'shipTo': {'fullName': 'Recipient name', 'contactAddress': {
                'addressLine1': 'Shipping street', 'addressLine2': 'Near exchange',
            }}, 'shippingServiceCode': 'ExpeditedInternational',
        }, 'maxEstimatedDeliveryDate': '2026-08-21T07:00:00.000Z'}],
        'pricingSummary': {'deliveryCost': {'value': '0.0', 'currency': 'USD'},
                           'total': {'value': '1450.0', 'currency': 'USD'}},
        'paymentSummary': {'totalDueSeller': {'value': '1259.21', 'currency': 'USD'},
                           'refunds': [{'amount': {'value': '50', 'currency': 'USD'}, 'refundStatus': 'SUCCEEDED'}]},
        'lineItems': [{'quantity': 1, 'title': 'Fan', 'lineItemFulfillmentInstructions': {
            'shipByDate': '2026-08-07T18:29:59.000Z',
        }}],
        'fulfillmentHrefs': ['private-provider-link'],
    }
    result = extract_order_details(order(payload))
    sections = {section['title']: {row['label']: row['value'] for row in section['rows']}
                for section in result['sections']}
    assert sections['Buyer registration']['Name'] == 'Buyer name'
    assert sections['Shipping recipient 1']['Name'] == 'Recipient name'
    assert sections['Shipping recipient 1']['Address'] == 'Shipping street\nNear exchange'
    assert sections['Order totals']['Shipping cost'] == '0.0 USD'
    assert sections['Order totals']['Order total'] == '1450.0 USD'
    assert sections['Order totals']['Seller proceeds'] == '1259.21 USD'
    assert sections['Order']['Cancellation status'] == 'NONE_REQUESTED'
    assert sections['Refund 1']['Amount'] == '50 USD'
    assert sections['Order item 1']['Quantity'] == '1'
    assert sections['Order item 1']['Ship by'] == '2026-08-07T18:29:59.000Z'
    assert 'private-provider-link' not in str(result)
    assert payload['buyer']['buyerRegistrationAddress']['fullName'] == 'Buyer name'


def test_empty_and_malformed_payloads_hide_empty_sections():
    for payload in (None, {}, {'buyer': [], 'lineItems': [None], 'pricingSummary': 'invalid'}):
        assert extract_order_details(order(payload))['sections'] == []


def test_only_matching_account_and_buyer_can_be_exposed():
    account_id = uuid4()
    conversation = SimpleNamespace(provider_account_id=account_id, buyer_identifier='Buyer')
    matching = order({'orderPaymentStatus': 'PAID'}, account_id=account_id, buyer_username='buyer')
    foreign_account = order(account_id=uuid4(), buyer_username='buyer')
    foreign_buyer = order(account_id=account_id, buyer_username='someone-else')
    service = ConversationAdditionalDetailsService(Mock())
    service.context_service = Mock()
    service.context_service.context_for_conversation.return_value = {
        'selected_order': None, 'candidate_orders': [matching, foreign_account, foreign_buyer],
    }
    assert len(service.get_details(conversation)['orders']) == 1
    service.context_service.context_for_conversation.return_value = {
        'selected_order': foreign_account, 'candidate_orders': [matching],
    }
    assert service.get_details(conversation) == {'orders': []}


def test_endpoint_does_not_mark_read_or_change_order_mapping(monkeypatch):
    from app.api.v1.routes import conversations as routes
    conversation_service = Mock()
    extra_service = Mock()
    extra_service.get_details.return_value = {'orders': []}
    monkeypatch.setattr(routes, 'ConversationService', Mock(return_value=conversation_service))
    monkeypatch.setattr(routes, 'ConversationAdditionalDetailsService', Mock(return_value=extra_service))
    conversation_id = uuid4()
    db = Mock()
    result = routes.get_conversation_additional_details(conversation_id, db, Mock())
    assert result.orders == []
    conversation_service.get_conversation.assert_called_once_with(conversation_id)
    conversation_service.mark_read.assert_not_called()
    db.commit.assert_not_called()


def test_return_status_and_stored_refund_are_shown_for_the_linked_order():
    returned = SimpleNamespace(
        return_id='return-123', return_status='RETURN_REQUESTED',
        return_state='OPEN', return_reason='DEFECTIVE_ITEM',
        created_date=datetime(2026, 10, 10, 10, 0, tzinfo=UTC),
    )
    result = extract_order_details(order(
        {'refundStatus': 'PARTIALLY_REFUNDED'},
        returns=[returned], refund_status='PARTIALLY_REFUNDED',
        refunds=[{'refundId': 'refund-456', 'amount': {'value': '25.00', 'currency': 'USD'},
                  'refundStatus': 'SUCCEEDED', 'refundDate': '2026-10-10T10:00:00Z'}],
    ))
    sections = {section['title']: {row['label']: row['value'] for row in section['rows']}
                for section in result['sections']}
    assert sections['Return 1'] == {
        'Return ID': 'return-123', 'Status': 'RETURN_REQUESTED', 'State': 'OPEN',
        'Reason': 'DEFECTIVE_ITEM', 'Opened': '2026-10-10T10:00:00+00:00',
    }
    assert sections['Refund status']['Status'] == 'PARTIALLY_REFUNDED'
    assert sections['Refund 1']['Refund ID'] == 'refund-456'
    assert sections['Refund 1']['Amount'] == '25.00 USD'
    assert sections['Refund 1']['Status'] == 'SUCCEEDED'


def test_return_without_refund_does_not_imply_a_refund():
    returned = SimpleNamespace(return_id='return-123', return_status='OPEN',
                               return_state=None, return_reason=None, created_date=None)
    result = extract_order_details(order(returns=[returned], refunds=[], refund_status=None))
    assert [section['title'] for section in result['sections']] == ['Return 1']
    assert [row['label'] for row in result['sections'][0]['rows']] == ['Return ID', 'Status']


def test_empty_provider_refunds_fall_back_to_stored_refunds():
    result = extract_order_details(order(
        {'paymentSummary': {'refunds': []}},
        refunds=[{'amount': {'value': '0', 'currency': 'USD'}}],
    ))
    assert result['sections'] == [{'title': 'Refund 1', 'rows': [{'label': 'Amount', 'value': '0 USD'}]}]
