"""Interpret provider evidence without turning an agreement into a paid offer."""
from datetime import timedelta

OPEN_STATUSES = {'ACTIVE', 'PENDING', 'COUNTERED'}
AGREED_STATUSES = {'SELLERACCEPT', 'PENDINGBUYERCONFIRMATION', 'PENDINGBUYERPAYMENT'}
CLOSED_STATUSES = {'DECLINED', 'EXPIRED', 'RETRACTED', 'WITHDRAWN', 'ADMINENDED'}
STATUS_LABELS = {
    'ACTIVE': 'Active', 'PENDING': 'Pending', 'COUNTERED': 'Countered',
    'SELLERACCEPT': 'Seller accepted', 'PENDINGBUYERCONFIRMATION': 'Awaiting buyer confirmation',
    'PENDINGBUYERPAYMENT': 'Awaiting buyer payment', 'ACCEPTED': 'Accepted',
    'DECLINED': 'Declined', 'EXPIRED': 'Expired', 'RETRACTED': 'Retracted',
    'WITHDRAWN': 'Withdrawn', 'ADMINENDED': 'Ended by eBay',
}


def status_key(value):
    return str(value or '').strip().upper()


def status_group(value):
    key = status_key(value)
    if key in OPEN_STATUSES:
        return 'OPEN'
    if key in AGREED_STATUSES:
        return 'AGREED'
    if key == 'ACCEPTED':
        return 'COMPLETED'
    if key in CLOSED_STATUSES:
        return 'CLOSED'
    return 'UNKNOWN'


def status_label(value):
    return STATUS_LABELS.get(status_key(value), str(value or 'Unknown'))


def reconciliation_delay(statuses, *, unresolved=False, returned=0):
    keys = {status_key(value) for value in statuses}
    if unresolved or keys & (OPEN_STATUSES | (AGREED_STATUSES - {'PENDINGBUYERPAYMENT'})):
        return timedelta(minutes=5)
    if 'PENDINGBUYERPAYMENT' in keys:
        return timedelta(minutes=15)
    if any(status_group(key) == 'UNKNOWN' for key in keys):
        return timedelta(hours=1)
    return timedelta(days=7) if returned else timedelta(hours=12)
