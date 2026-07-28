from app.modules.sold_posting.models import SoldPostingStatus


def normalize_sold_posting_status(order: dict) -> SoldPostingStatus:
    cancel_state = str((order.get('cancelStatus') or {}).get('cancelState') or '').upper()
    payment_status = str(order.get('orderPaymentStatus') or '').upper()
    fulfillment_status = str(order.get('orderFulfillmentStatus') or '').upper()
    refunds = ((order.get('paymentSummary') or {}).get('refunds') or [])
    line_refunds = [refund for item in order.get('lineItems') or [] for refund in item.get('refunds') or []]

    if cancel_state in {
        'CANCELLED',
        'CANCEL_REQUESTED',
        'CANCEL_PENDING',
        'CANCEL_IN_PROGRESS',
        'CANCEL_COMPLETE',
        'CANCEL_COMPLETED',
    }:
        return SoldPostingStatus.CANCELLED
    if _has_full_refund(order, refunds, line_refunds):
        return SoldPostingStatus.REFUNDED
    if refunds or line_refunds:
        return SoldPostingStatus.PARTIALLY_REFUNDED
    if payment_status in {'NOT_PAID', 'PENDING', 'FAILED'}:
        return SoldPostingStatus.AWAITING_PAYMENT
    if payment_status in {'PAID', 'FULLY_PAID'} and fulfillment_status in {'NOT_STARTED', 'READY_FOR_SHIPMENT'}:
        return SoldPostingStatus.AWAITING_SHIPMENT
    if payment_status in {'PAID', 'FULLY_PAID'} and fulfillment_status in {'IN_PROGRESS', 'PARTIALLY_FULFILLED'}:
        return SoldPostingStatus.PARTIALLY_SHIPPED
    if fulfillment_status in {'FULFILLED', 'SHIPPED'}:
        return SoldPostingStatus.SHIPPED
    return SoldPostingStatus.OTHER


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
