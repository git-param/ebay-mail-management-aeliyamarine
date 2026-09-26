"""Database-only buyer, seller and historical offer view. No token service or provider client dependency."""
from datetime import UTC, datetime, timedelta
from decimal import Decimal, InvalidOperation
from sqlalchemy import select, func, or_, Numeric, cast
from app.models.offer import Offer
from app.models.ebay_account import EbayAccount
from app.models.ebay_best_offer_action import EbayBestOfferAction
from app.models.conversation import Conversation
from app.models.order_context import ConversationProductContext


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
             role=None, sort='expiring', page=1, page_size=25, can_respond=False):
        display_status = func.coalesce(Offer.provider_status, Offer.status)
        criteria = [Offer.provider == 'EBAY', Offer.record_source != 'DERIVED',
                    ~Offer.provider_offer_id.like('%:seller-counteroffer-submitted')]
        if role == 'Unknown':
            criteria.append(Offer.provider_role.is_(None))
        elif role:
            criteria.append(Offer.provider_role == role)
        if account_id:
            criteria.append(Offer.account_id == account_id)
        if status:
            criteria.append(display_status == status)
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
        cached = {}
        contexts = self.db.execute(select(Conversation.provider_account_id, ConversationProductContext)
            .join(Conversation, Conversation.id == ConversationProductContext.conversation_id)
            .where(Conversation.provider_account_id.in_({o.account_id for o in offers}),
                   ConversationProductContext.reference_id.in_({o.listing_id for o in offers if o.listing_id}))
            .order_by(ConversationProductContext.updated_at.desc()))
        for cached_account, context in contexts:
            cached.setdefault((cached_account, context.reference_id), context)
        items = []
        for offer in offers:
            raw, listing = offer.provider_snapshot or offer.raw_payload or {}, offer.listing_snapshot or {}
            context = cached.get((offer.account_id, offer.listing_id))
            if context:
                metadata = {'title': context.item_title, 'image_url': context.image_url, 'sku': context.sku,
                    'price': str(context.price_value) if context.price_value is not None else None,
                    'currency': context.price_currency}
                listing = {**{k:v for k,v in metadata.items() if v is not None}, **listing}
            account, action = accounts.get(offer.account_id), latest.get(offer.id)
            items.append({'id': offer.id, 'account_id': offer.account_id,
                'account_name': account.account_name if account else None,
                'provider_offer_id': offer.provider_offer_id, 'listing_id': offer.listing_id,
                'buyer': raw.get('buyerUsername') or offer.buyer_username, 'seller': raw.get('sellerUsername'),
                'provider_status': offer.provider_status, 'display_status': offer.provider_status or offer.status,
                'record_source': offer.record_source, 'status_verified': bool(offer.provider_snapshot),
                'provider_role': offer.provider_role, 'amount': raw.get('amount') if raw.get('amount') is not None else offer.offer_amount, 'currency': raw.get('currency') or offer.currency,
                'quantity': raw.get('quantity'), 'buyer_message': raw.get('buyerMessage'),
                'listing': listing, 'received_at': offer.received_at, 'received_at_source': offer.received_at_source,
                'first_seen_at': offer.first_seen_at, 'expires_at': offer.expires_at,
                'last_synced_at': offer.last_synced_at, 'version': offer.version,
                'reconciliation_required': offer.reconciliation_required,
                'last_action': {'action': action.action, 'state': action.state, 'id': action.id} if action else None,
                'can_respond': can_respond and bool(account and account.is_active and account.connection_status.value == 'CONNECTED') and actionable(offer, action)})
        summary = dict(self.db.execute(select(display_status, func.count()).where(*criteria).group_by(display_status)).all())
        summary['ExpiringSoon'] = self.db.scalar(select(func.count()).select_from(Offer).where(*criteria,
            Offer.provider_status.in_(['Active','Pending']), Offer.expires_at > datetime.now(UTC),
            Offer.expires_at <= datetime.now(UTC) + timedelta(hours=4)))
        statuses = list(self.db.scalars(select(display_status).where(Offer.provider == 'EBAY', Offer.record_source != 'DERIVED').distinct().order_by(display_status)))
        return {'items': items, 'total': total, 'page': page, 'page_size': page_size, 'summary': summary, 'statuses': statuses}
