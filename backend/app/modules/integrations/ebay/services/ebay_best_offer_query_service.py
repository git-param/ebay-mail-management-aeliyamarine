"""Database-only seller view. No token service or provider client dependency."""
from datetime import UTC, datetime, timedelta
from decimal import Decimal, InvalidOperation
from sqlalchemy import select, func, or_, Numeric, cast
from app.models.offer import Offer
from app.models.ebay_account import EbayAccount
from app.models.ebay_best_offer_action import EbayBestOfferAction


def actionable(offer, last_action=None):
    raw = offer.provider_snapshot or {}
    expires = offer.expires_at
    try:
        amount = Decimal(str(raw.get('amount')))
        quantity = int(raw.get('quantity'))
        verified_values = amount.is_finite() and amount > 0 and quantity > 0 and str(quantity) == str(raw.get('quantity'))
    except (InvalidOperation, ValueError, TypeError):
        verified_values = False
    return bool(verified_values and not offer.provider_offer_id.endswith(':seller-counteroffer-submitted')
        and not raw.get('derivedEvent') and offer.record_source == 'TRADING' and offer.provider_role == 'Seller'
        and raw.get('offerType') in {'BuyerBestOffer', 'BuyerCounterOffer'}
        and offer.provider_status in {'Active', 'Pending'}
        and offer.listing_id and raw.get('currency') and raw.get('amount') is not None
        and raw.get('quantity') and expires and expires > datetime.now(UTC)
        and not offer.reconciliation_required
        and (last_action is None or last_action.state in {'FAILED','RECONCILED'}))


class EbayBestOfferQueryService:
    def __init__(self, db):
        self.db = db

    def list(self, *, account_id=None, status=None, search=None, buyer=None, item_id=None,
             sort='expiring', page=1, page_size=25, can_respond=False):
        criteria = [Offer.provider == 'EBAY', Offer.record_source == 'TRADING', Offer.provider_role == 'Seller']
        if account_id:
            criteria.append(Offer.account_id == account_id)
        if status:
            criteria.append(Offer.provider_status == status)
        if buyer:
            criteria.append(Offer.buyer_username.ilike('%' + buyer + '%'))
        if item_id:
            criteria.append(Offer.listing_id == item_id)
        if search:
            needle = '%' + search + '%'
            criteria.append(or_(Offer.listing_id.ilike(needle), Offer.provider_offer_id.ilike(needle),
                Offer.buyer_username.ilike(needle), Offer.listing_snapshot['title'].astext.ilike(needle),
                Offer.listing_snapshot['sku'].astext.ilike(needle)))
        base = select(Offer).where(*criteria)
        total = self.db.scalar(select(func.count()).select_from(base.subquery()))
        order = {'expiring': Offer.expires_at.asc().nulls_last(), 'newest': Offer.first_seen_at.desc(),
                 'amount': Offer.offer_amount.desc().nulls_last(),
                 'listing_price': cast(Offer.listing_snapshot['price'].astext, Numeric).desc().nulls_last()}[sort]
        offers = list(self.db.scalars(base.order_by(order, Offer.id).offset((page-1)*page_size).limit(page_size)))
        accounts = {a.id: a for a in self.db.scalars(select(EbayAccount).where(EbayAccount.id.in_({o.account_id for o in offers})))}
        latest = {}
        for action in self.db.scalars(select(EbayBestOfferAction).where(
            EbayBestOfferAction.offer_id.in_([o.id for o in offers])).order_by(EbayBestOfferAction.created_at.desc())):
            latest.setdefault(action.offer_id, action)
        items = []
        for offer in offers:
            raw, listing = offer.provider_snapshot or {}, offer.listing_snapshot or {}
            account, action = accounts.get(offer.account_id), latest.get(offer.id)
            items.append({'id': offer.id, 'account_id': offer.account_id,
                'account_name': account.account_name if account else None,
                'provider_offer_id': offer.provider_offer_id, 'listing_id': offer.listing_id,
                'buyer': raw.get('buyerUsername'), 'provider_status': offer.provider_status,
                'provider_role': offer.provider_role, 'amount': raw.get('amount'), 'currency': raw.get('currency'),
                'quantity': raw.get('quantity'), 'buyer_message': raw.get('buyerMessage'),
                'listing': listing, 'received_at': offer.received_at, 'received_at_source': offer.received_at_source,
                'first_seen_at': offer.first_seen_at, 'expires_at': offer.expires_at,
                'last_synced_at': offer.last_synced_at, 'version': offer.version,
                'reconciliation_required': offer.reconciliation_required,
                'last_action': {'action': action.action, 'state': action.state, 'id': action.id} if action else None,
                'can_respond': can_respond and bool(account and account.is_active and account.connection_status.value == 'CONNECTED') and actionable(offer, action)})
        summary = dict(self.db.execute(select(Offer.provider_status, func.count()).where(*criteria).group_by(Offer.provider_status)).all())
        summary['ExpiringSoon'] = self.db.scalar(select(func.count()).select_from(Offer).where(*criteria,
            Offer.provider_status.in_(['Active','Pending']), Offer.expires_at > datetime.now(UTC),
            Offer.expires_at <= datetime.now(UTC) + timedelta(hours=4)))
        statuses = list(self.db.scalars(select(Offer.provider_status).where(Offer.record_source == 'TRADING',
            Offer.provider_role == 'Seller', Offer.provider_status.is_not(None)).distinct().order_by(Offer.provider_status)))
        return {'items': items, 'total': total, 'page': page, 'page_size': page_size, 'summary': summary, 'statuses': statuses}
