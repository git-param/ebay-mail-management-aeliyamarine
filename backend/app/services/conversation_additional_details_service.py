from app.services.order_context_service import OrderContextService


def text(value):
    if not isinstance(value, (str, int, float)) or isinstance(value, bool):
        return ''
    return str(value).strip()


def obj(value):
    return value if isinstance(value, dict) else {}


def records(value):
    return [item for item in value if isinstance(item, dict)] if isinstance(value, list) else []


def money(value):
    value = obj(value)
    amount = text(value.get('value'))
    return ' '.join(filter(None, [amount, text(value.get('currency'))])) if amount else ''


def extract_order_details(order):
    """Expose useful support fields, never the complete provider payload."""
    payload = obj(order.raw_payload)
    sections = []

    def section(title, pairs):
        rows = [{'label': label, 'value': text(value)} for label, value in pairs if text(value)]
        if rows:
            sections.append({'title': title, 'rows': rows})

    def contact(title, data):
        data = obj(data)
        address = obj(data.get('contactAddress'))
        section(title, [
            ('Name', data.get('fullName')),
            ('Email', data.get('email')),
            ('Phone', obj(data.get('primaryPhone')).get('phoneNumber')),
            ('Address', '\n'.join(filter(None, [text(address.get(key)) for key in (
                'addressLine1', 'addressLine2', 'city', 'stateOrProvince', 'postalCode', 'countryCode',
            )]))),
        ])

    buyer = obj(payload.get('buyer'))
    contact('Buyer registration', buyer.get('buyerRegistrationAddress'))
    tax = obj(buyer.get('taxAddress'))
    section('Buyer tax location', [('Country', tax.get('countryCode')), ('State / province', tax.get('stateOrProvince'))])
    section('Order', [
        ('Placed', payload.get('creationDate')),
        ('Last updated', payload.get('lastModifiedDate')),
        ('Payment status', payload.get('orderPaymentStatus') or order.payment_status),
        ('Fulfillment status', payload.get('orderFulfillmentStatus') or order.fulfillment_status),
        ('Cancellation status', obj(payload.get('cancelStatus')).get('cancelState') or order.cancel_status),
        ('Sales record', payload.get('salesRecordReference')),
    ])
    for index, instruction in enumerate(records(payload.get('fulfillmentStartInstructions')), 1):
        shipping = obj(instruction.get('shippingStep'))
        contact(f'Shipping recipient {index}', shipping.get('shipTo'))
        section(f'Delivery {index}', [
            ('Service', shipping.get('shippingServiceCode')),
            ('Estimated from', instruction.get('minEstimatedDeliveryDate')),
            ('Estimated by', instruction.get('maxEstimatedDeliveryDate')),
        ])
    pricing = obj(payload.get('pricingSummary')) or obj(order.pricing_summary)
    summary = obj(payload.get('paymentSummary'))
    section('Order totals', [
        ('Subtotal', money(pricing.get('priceSubtotal'))),
        ('Shipping cost', money(pricing.get('deliveryCost'))),
        ('Tax', money(pricing.get('tax'))),
        ('Order total', money(pricing.get('total'))),
        ('Marketplace fees', money(payload.get('totalMarketplaceFee'))),
        ('Seller proceeds', money(summary.get('totalDueSeller'))),
    ])
    for index, payment in enumerate(records(summary.get('payments')), 1):
        section(f'Payment {index}', [
            ('Amount', money(payment.get('amount'))), ('Status', payment.get('paymentStatus')),
            ('Method', payment.get('paymentMethod')), ('Paid on', payment.get('paymentDate')),
        ])
    for index, refund in enumerate(records(summary.get('refunds') or payload.get('refunds')), 1):
        section(f'Refund {index}', [
            ('Amount', money(refund.get('amount'))), ('Status', refund.get('refundStatus')),
            ('Date', refund.get('refundDate')), ('Reason', refund.get('refundReason')),
        ])
    for index, item in enumerate(records(payload.get('lineItems')), 1):
        delivery = obj(item.get('lineItemFulfillmentInstructions'))
        section(f'Order item {index}', [
            ('Title', item.get('title')), ('Item number', item.get('legacyItemId') or item.get('itemId')),
            ('SKU', item.get('sku')), ('Quantity', item.get('quantity')),
            ('Item total', money(item.get('total'))), ('Fulfillment', item.get('lineItemFulfillmentStatus')),
            ('Ship by', delivery.get('shipByDate')),
            ('Estimated from', delivery.get('minEstimatedDeliveryDate')),
            ('Estimated by', delivery.get('maxEstimatedDeliveryDate')),
        ])
    return {'order_id': order.order_id, 'sections': sections}


class ConversationAdditionalDetailsService:
    def __init__(self, db):
        self.context_service = OrderContextService(db)

    def get_details(self, conversation):
        context = self.context_service.context_for_conversation(conversation)
        selected = context['selected_order']
        orders = [selected] if selected else context['candidate_orders']
        # Do not expose contact information from another account or buyer.
        matching = [order for order in orders
                    if order.account_id == conversation.provider_account_id
                    and text(order.buyer_username).casefold() == text(conversation.buyer_identifier).casefold()
                    and text(conversation.buyer_identifier)]
        return {'orders': [extract_order_details(order) for order in matching]}
