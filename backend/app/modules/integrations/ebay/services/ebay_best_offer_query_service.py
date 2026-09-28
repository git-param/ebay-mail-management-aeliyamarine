"""Database-only buyer, seller and historical offer view. No token service or provider client dependency."""
from datetime import UTC, datetime, timedelta
from decimal import Decimal, InvalidOperation
from sqlalchemy import select, func, or_, Numeric, String, cast, case
from sqlalchemy.orm import aliased
from app.models.offer import Offer
from app.models.ebay_account import EbayAccount
from app.models.ebay_best_offer_action import EbayBestOfferAction
from app.models.conversation import Conversation
from app.models.order_context import ConversationProductContext
from app.modules.integrations.ebay.services.ebay_best_offer_snapshot import current_snapshot_ids
from app.modules.integrations.ebay.services.ebay_best_offer_status import (
    OPEN_STATUSES, AGREED_STATUSES, CLOSED_STATUSES, status_group, status_label, status_key,
)


def latest_offer_ids(criteria):
    item_key = func.coalesce(func.nullif(func.trim(Offer.listing_id), ''), cast(Offer.id, String))
    buyer_key = func.coalesce(func.nullif(func.lower(func.trim(Offer.buyer_username)), ''), cast(Offer.id, String))
    # Bulk-imported legacy rows can differ only by insertion microseconds.
    # Use provider time when known, then offer ID to break import-time ties.
    latest_at = func.coalesce(Offer.created_at_provider, Offer.received_at,
        func.date_trunc('second', Offer.first_seen_at), Offer.created_at)
    numeric_id = case((Offer.provider_offer_id.op('~')('^[0-9]+$'), cast(Offer.provider_offer_id, Numeric)), else_=None)
    ranked = select(Offer.id, func.row_number().over(
        partition_by=(Offer.account_id, item_key, buyer_key),
        order_by=(latest_at.desc(), numeric_id.desc().nulls_last(), Offer.created_at.desc(), Offer.id.desc()),
    ).label('position')).where(*criteria).subquery()
    return select(ranked.c.id).where(ranked.c.position == 1)


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

    def list(self, *, account_id=None, status=None, lifecycle=None, view='current', search=None, buyer=None, item_id=None,
             role=None, sort='expiring', page=1, page_size=25, can_respond=False):
        display_status = func.coalesce(Offer.provider_status, Offer.status)
        normalized_status = func.upper(func.trim(display_status))
        criteria = [Offer.provider == 'EBAY', Offer.record_source != 'DERIVED',
                    ~Offer.provider_offer_id.like('%:seller-counteroffer-submitted')]
        snapshots = []
        if view == 'current':
            all_snapshot_ids, _ = current_snapshot_ids(self.db)
            snapshot_ids, snapshots = current_snapshot_ids(self.db, account_id)
            # Unpublished open rows from a failed paginated scan must not replace
            # the last complete snapshot. Terminal evidence still closes old steps.
            criteria.append(or_(Offer.id.in_(all_snapshot_ids),
                normalized_status.in_(CLOSED_STATUSES | {'ACCEPTED'})))
        # Rank before applying any user filters. Otherwise filtering Pending can
        # incorrectly resurrect an older Pending offer after a newer acceptance.
        criteria = [Offer.id.in_(latest_offer_ids(criteria))]
        if view == 'current':
            criteria.append(Offer.id.in_(snapshot_ids))
            # A newer negotiation step can be verified through the other managed
            # account. Do not resurrect an older step still in its snapshot.
            newer = aliased(Offer)
            newer_number = case((newer.provider_offer_id.op('~')('^[0-9]+$'), cast(newer.provider_offer_id, Numeric)), else_=None)
            own_number = case((Offer.provider_offer_id.op('~')('^[0-9]+$'), cast(Offer.provider_offer_id, Numeric)), else_=None)
            newer_at = func.coalesce(newer.created_at_provider, newer.received_at,
                func.date_trunc('second', newer.first_seen_at), newer.created_at)
            own_at = func.coalesce(Offer.created_at_provider, Offer.received_at,
                func.date_trunc('second', Offer.first_seen_at), Offer.created_at)
            criteria.append(~select(newer.id).where(
                newer.provider == 'EBAY', newer.record_source == 'TRADING',
                newer.provider_role.in_(['Seller', 'Buyer']),
                or_(newer.id.in_(all_snapshot_ids),
                    func.upper(func.trim(newer.provider_status)).in_(CLOSED_STATUSES | {'ACCEPTED'})),
                newer.listing_id == Offer.listing_id,
                func.lower(func.trim(newer.buyer_username)) == func.lower(func.trim(Offer.buyer_username)),
                newer.provider_offer_id != Offer.provider_offer_id,
                or_(newer_at > own_at, (newer_at == own_at) & (newer_number > own_number)),
            ).exists())
            criteria.append(~normalized_status.in_(CLOSED_STATUSES | {'ACCEPTED'}))
        else:
            criteria.append(~normalized_status.in_(OPEN_STATUSES | AGREED_STATUSES))
        visible_criteria = list(criteria)
        if role == 'Unknown':
            criteria.append(Offer.provider_role.is_(None))
        elif role:
            criteria.append(Offer.provider_role == role)
        if account_id:
            criteria.append(Offer.account_id == account_id)
        if status:
            criteria.append(normalized_status == status_key(status))
        if lifecycle:
            group_expression = case((normalized_status.in_(OPEN_STATUSES), 'OPEN'),
                (normalized_status.in_(AGREED_STATUSES), 'AGREED'),
                (normalized_status == 'ACCEPTED', 'COMPLETED'),
                (normalized_status.in_(CLOSED_STATUSES), 'CLOSED'), else_='UNKNOWN')
            criteria.append(group_expression == lifecycle)
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
            seller = raw.get('sellerUsername') or (account.ebay_username if account and offer.provider_role == 'Seller' else None)
            buyer_name = raw.get('buyerUsername') or offer.buyer_username
            offer_type = raw.get('offerType')
            seller_sent = offer_type in {'SellerCounterOffer', 'SellerBestOffer', 'SellerOffer'}
            buyer_sent = offer_type in {'BuyerBestOffer', 'BuyerCounterOffer'}
            items.append({'id': offer.id, 'account_id': offer.account_id,
                'account_name': account.account_name if account else None,
                'provider_offer_id': offer.provider_offer_id, 'listing_id': offer.listing_id,
                'buyer': buyer_name, 'seller': seller, 'offer_type': offer_type,
                'offer_from': seller if seller_sent else buyer_name if buyer_sent else None,
                'offer_to': buyer_name if seller_sent else seller if buyer_sent else None,
                'provider_status': offer.provider_status, 'status': offer.status,
                'display_status': status_label(offer.provider_status or offer.status),
                'status_group': status_group(offer.provider_status or offer.status),
                'record_source': offer.record_source, 'status_verified': bool(offer.provider_snapshot),
                'provider_role': offer.provider_role, 'amount': raw.get('amount') if raw.get('amount') is not None else offer.offer_amount, 'currency': raw.get('currency') or offer.currency,
                'quantity': raw.get('quantity'), 'buyer_message': raw.get('buyerMessage'),
                'listing': listing, 'received_at': offer.received_at, 'received_at_source': offer.received_at_source,
                'first_seen_at': offer.first_seen_at, 'expires_at': offer.expires_at,
                'last_synced_at': offer.last_synced_at, 'version': offer.version,
                'reconciliation_required': offer.reconciliation_required,
                'last_action': {'action': action.action, 'state': action.state, 'id': action.id} if action else None,
                'can_respond': view == 'current' and can_respond and bool(account and account.is_active and account.connection_status.value == 'CONNECTED') and actionable(offer, action)})
        summary = dict(self.db.execute(select(display_status, func.count()).where(*criteria).group_by(display_status)).all())
        groups = {key: 0 for key in ('OPEN', 'AGREED', 'COMPLETED', 'CLOSED', 'UNKNOWN')}
        for value, count in summary.items():
            groups[status_group(value)] += count
        summary['ExpiringSoon'] = self.db.scalar(select(func.count()).select_from(Offer).where(*criteria,
            normalized_status.in_(OPEN_STATUSES), Offer.expires_at > datetime.now(UTC),
            Offer.expires_at <= datetime.now(UTC) + timedelta(hours=4)))
        statuses = sorted({status_key(value) for value in self.db.scalars(select(display_status).where(*visible_criteria).distinct()) if status_key(value)})
        return {'items': items, 'total': total, 'page': page, 'page_size': page_size, 'summary': summary,
            'status_groups': groups, 'statuses': statuses, 'view': view, 'snapshots': snapshots,
            'status_options': [{'value': value, 'label': status_label(value), 'group': status_group(value)} for value in statuses]}
