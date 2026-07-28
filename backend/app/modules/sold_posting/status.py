from app.modules.sold_posting.models import SoldPostingStatus


def normalize_sold_posting_status(order: dict) -> SoldPostingStatus:
    cancel_state = str((order.get('cancelStatus') or {}).get('cancelState') or '').upper()
    payment_status = str(order.get('orderPaymentStatus') or '').upper()
    fulfillment_status = str(order.get('orderFulfillmentStatus') or '').upper()
    refunds = ((order.get('paymentSummary') or {}).get('refunds') or [])
    line_refunds = [refund for item in order.get('lineItems') or [] for refund in item.get('refunds') or []]

    if _is_cancelled(order, cancel_state):
        return SoldPostingStatus.CANCELLED
    if _has_full_refund(order, refunds, line_refunds) or refunds or line_refunds:
        return SoldPostingStatus.REFUNDED
    if _has_delivered_signal(order):
        return SoldPostingStatus.DELIVERED
    if payment_status in {'NOT_PAID', 'PENDING', 'FAILED'}:
        return SoldPostingStatus.AWAITING_PAYMENT
    if payment_status in {'PAID', 'FULLY_PAID', 'PAID_IN_FULL'} and fulfillment_status in {'NOT_STARTED', 'READY_FOR_SHIPMENT'}:
        return SoldPostingStatus.AWAITING_SHIPMENT
    if payment_status in {'PAID', 'FULLY_PAID', 'PAID_IN_FULL'} and fulfillment_status in {'IN_PROGRESS', 'PARTIALLY_FULFILLED', 'PARTIALLY_SHIPPED'}:
        return SoldPostingStatus.SHIPPED
    if fulfillment_status in {'FULFILLED', 'SHIPPED', 'FULLY_FULFILLED'}:
        return SoldPostingStatus.SHIPPED
    return SoldPostingStatus.OTHER


def _is_cancelled(order: dict, cancel_state: str) -> bool:
    if cancel_state in {
        'CANCELLED',
        'CANCELED',
        'CANCEL_REQUESTED',
        'CANCELLATION_REQUESTED',
        'CANCEL_PENDING',
        'CANCELLATION_PENDING',
        'CANCEL_IN_PROGRESS',
        'CANCELLATION_IN_PROGRESS',
        'CANCEL_COMPLETE',
        'CANCEL_COMPLETED',
        'CANCELLATION_COMPLETE',
        'CANCELLATION_COMPLETED',
    }:
        return True
    cancel_status = order.get('cancelStatus') or {}
    request_nodes = []
    for key in ['cancelRequests', 'cancellationRequests']:
        value = cancel_status.get(key)
        if isinstance(value, list):
            request_nodes.extend(value)
        elif isinstance(value, dict):
            request_nodes.append(value)
    active_or_completed = {
        'CANCELLED',
        'CANCELED',
        'REQUESTED',
        'PENDING',
        'IN_PROGRESS',
        'COMPLETE',
        'COMPLETED',
        'CANCEL_COMPLETE',
        'CANCEL_COMPLETED',
    }
    benign = {'REJECTED', 'DECLINED', 'CLOSED', 'CANCEL_CLOSED', 'CANCEL_REQUEST_REJECTED'}
    for node in request_nodes:
        values = {_normalize_text(value) for value in node.values() if isinstance(value, str)}
        if values & benign:
            continue
        if values & active_or_completed:
            return True
    return False


def _has_delivered_signal(order: dict) -> bool:
    delivered_keys = {
        'deliverystatus',
        'shipmenttrackingstatus',
        'shippingstatus',
        'status',
        'lineitemfulfillmentstatus',
    }
    for key, value in _walk(order):
        normalized_key = key.lower().replace('_', '')
        normalized_value = _normalize_text(value)
        if normalized_key in delivered_keys and normalized_value in {'DELIVERED', 'DELIVERY_COMPLETE', 'DELIVERY_COMPLETED'}:
            return True
        if normalized_key in {'actualdeliverydate', 'delivereddatetz', 'delivereddate'} and value:
            return True
    return False


def _has_full_refund(order: dict, refunds: list, line_refunds: list) -> bool:
    order_total = _money_value((order.get('pricingSummary') or {}).get('total'))
    refund_total = sum((_money_value(refund.get('amount')) or 0) for refund in refunds)
    refund_total += sum((_money_value(refund.get('amount')) or 0) for refund in line_refunds)
    return bool(order_total and refund_total >= order_total)


def _money_value(node: dict | None) -> float | None:
    if not isinstance(node, dict):
        return None
    value = node.get('value')
    try:
        return float(value) if value not in (None, '') else None
    except (TypeError, ValueError):
        return None


def _walk(value):
    if isinstance(value, dict):
        for key, item in value.items():
            yield str(key), item
            yield from _walk(item)
    elif isinstance(value, list):
        for item in value:
            yield from _walk(item)


def _normalize_text(value: object) -> str:
    return str(value or '').strip().upper()

