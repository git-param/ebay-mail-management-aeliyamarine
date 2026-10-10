from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime

from fastapi import HTTPException

from app.models.ebay_account import EbayAccount
from app.modules.integrations.ebay.oauth.token_service import EbayTokenService
from app.services.order_context_service import OrderContextService
from app.services.conversation_additional_details_service import obj, records, text, money


def date_value(value):
    return text(obj(value).get('value')) or text(value)


def serialize_live_return(summary, payload, order_id):
    detail = obj(payload.get('detail'))
    summary = {**summary, **obj(payload.get('summary'))}
    creation = obj(summary.get('creationInfo'))
    item = obj(detail.get('itemDetail'))
    actual = obj(obj(detail.get('refundInfo')).get('actualRefundDetail'))
    seller_refund = obj(summary.get('sellerTotalRefund'))
    buyer_refund = obj(summary.get('buyerTotalRefund'))
    due = obj(summary.get('sellerResponseDue'))
    sections = []

    def section(title, pairs):
        rows = [{'label': key, 'value': text(value)} for key, value in pairs if text(value)]
        if rows:
            sections.append({'title': title, 'rows': rows})

    section('Return status', [
        ('Status', summary.get('status')), ('State', summary.get('state')),
        ('Reason', creation.get('reason')), ('Reason type', creation.get('reasonType')),
        ('Opened', date_value(creation.get('creationDate'))),
        ('Buyer comment', obj(creation.get('comments')).get('content')),
        ('Action due', due.get('activityDue')), ('Respond by', date_value(due.get('respondByDate'))),
    ])
    section('Return item', [
        ('Title', item.get('itemTitle')),
        ('Item number', item.get('itemId') or obj(creation.get('item')).get('itemId')),
        ('Quantity', item.get('returnQuantity') or obj(creation.get('item')).get('returnQuantity')),
    ])
    section('Refund', [
        ('Status', actual.get('refundStatus')),
        ('Refunded amount', money(obj(actual.get('actualRefund')).get('totalAmount'))
         or money(buyer_refund.get('actualRefundAmount'))),
        ('Seller refund', money(seller_refund.get('actualRefundAmount'))),
        ('Estimated amount', money(seller_refund.get('estimatedRefundAmount'))),
        ('Issued', date_value(actual.get('refundIssuedDate'))),
    ])
    shipment = obj(detail.get('returnShipmentInfo'))
    trackings = records(shipment.get('allShipmentTrackings'))
    if not trackings and obj(shipment.get('shipmentTracking')):
        trackings = [shipment['shipmentTracking']]
    for index, tracking in enumerate(trackings, 1):
        section(f'Return shipping {index}', [
            ('Carrier', tracking.get('carrierUsed')), ('Tracking number', tracking.get('trackingNumber')),
            ('Delivery status', tracking.get('deliveryStatus')),
            ('Shipped', date_value(tracking.get('actualShipDate'))),
            ('Delivered', date_value(tracking.get('actualDeliveryDate'))),
        ])
    close = obj(detail.get('closeInfo'))
    section('Return closure', [('Reason', close.get('returnCloseReason')),
                               ('Closed', date_value(close.get('returnCloseDate')))])
    return {'return_id': text(summary.get('returnId')), 'order_id': order_id, 'sections': sections}


class ConversationLiveReturnsService:
    """Read returns from eBay on demand without persisting provider responses."""
    def __init__(self, db):
        self.db = db
        self.context = OrderContextService(db)

    def fetch(self, conversation, *, order_record_id=None, offset=0):
        context = self.context.context_for_conversation(conversation)
        selected = context['selected_order']
        orders = ([selected] if selected else []) + context['candidate_orders']
        if order_record_id:
            order = next((item for item in orders if item.id == order_record_id), None)
        else:
            order = selected or (orders[0] if len(orders) == 1 else None)
        if not order:
            raise HTTPException(422, 'Link or select an order before fetching return details.')
        if (order.account_id != conversation.provider_account_id
                or text(order.buyer_username).casefold() != text(conversation.buyer_identifier).casefold()
                or not text(conversation.buyer_identifier)):
            raise HTTPException(403, 'The order does not belong to this conversation buyer and account.')
        account = self.db.get(EbayAccount, conversation.provider_account_id)
        if not account or not account.is_active:
            raise HTTPException(400, 'The sending eBay account is unavailable or inactive.')
        environment = getattr(account.environment, 'value', account.environment)
        if environment != 'PRODUCTION':
            raise HTTPException(400, 'eBay return details are available for production accounts only.')
        tokens = EbayTokenService(self.db)
        tokens.client.environment = environment
        if not account.access_token or (account.access_token_expires_at and account.access_token_expires_at <= datetime.now(UTC)):
            account = tokens.refresh_access_token(account.id)
        items = records(obj(order.raw_payload).get('lineItems'))
        marketplace = next((text(item.get('listingMarketplaceId')) for item in items
                            if text(item.get('listingMarketplaceId'))), 'EBAY_US')

        def search():
            return tokens.client.search_returns_raw(account.access_token, order_id=order.order_id,
                                                     marketplace_id=marketplace, limit=10, offset=offset)

        response = search()
        if response.status_code == 401:
            account = tokens.refresh_access_token(account.id)
            response = search()
        if not response.ok:
            message = ('eBay denied return access. Check this account’s connection and Post-Order API access.'
                       if response.status_code in (401, 403) else
                       'eBay could not fetch return details. Please try again.')
            raise HTTPException(502, message)
        if not isinstance(response.payload, dict) or not isinstance(response.payload.get('members', []), list):
            raise HTTPException(502, 'eBay returned an invalid return search response.')
        members = records(response.payload.get('members'))
        # Always search by the server-resolved order; never trust a client order/return ID.
        members = [member for member in members if text(member.get('returnId'))
                   and (not member.get('orderId') or text(member['orderId']) == order.order_id)]

        def get_detail(summary):
            warning = None
            try:
                full = tokens.client.get_return_raw(account.access_token, return_id=text(summary['returnId']),
                                                     marketplace_id=marketplace)
                payload = full.payload if full.ok and isinstance(full.payload, dict) else {}
                full_summary = obj(payload.get('summary'))
                if ((full_summary.get('orderId') and text(full_summary['orderId']) != order.order_id)
                        or (full_summary.get('returnId') and text(full_summary['returnId']) != text(summary['returnId']))):
                    payload = {}
                if not obj(payload.get('detail')):
                    payload = {}
                if not payload:
                    warning = 'Full details are unavailable. Showing the live eBay summary.'
            except HTTPException:
                payload = {}
                warning = 'Full details are unavailable. Showing the live eBay summary.'
            result = serialize_live_return(summary, payload, order.order_id)
            result['warning'] = warning
            return result

        with ThreadPoolExecutor(max_workers=4) as executor:
            results = list(executor.map(get_detail, members))
        pagination = obj(response.payload.get('paginationOutput'))
        total = pagination.get('totalEntries', response.payload.get('total', 0))
        try:
            more = offset + 10 < int(total)
        except (ValueError, TypeError):
            more = False
        return {'order_id': order.order_id, 'returns': results, 'fetched_at': datetime.now(UTC),
                'next_offset': offset + 10 if more else None}
