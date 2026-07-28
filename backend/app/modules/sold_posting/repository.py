from datetime import UTC, date, datetime, time
from uuid import UUID

from sqlalchemy import func, or_
from sqlalchemy.orm import Session, joinedload

from app.models.ebay_account import EbayAccount
from app.models.order_context import ConversationProductContext, EbayOrderLineItem
from app.modules.sold_posting.models import SoldPostingLineItem, SoldPostingOrder, SoldPostingSyncState


class SoldPostingRepository:
    def __init__(self, db: Session):
        self.db = db

    def get_or_create_sync_state(self, account_id: UUID) -> SoldPostingSyncState:
        state = self.db.query(SoldPostingSyncState).filter(SoldPostingSyncState.ebay_account_id == account_id).first()
        if not state:
            state = SoldPostingSyncState(ebay_account_id=account_id)
            self.db.add(state)
            self.db.flush()
        return state

    def active_accounts(self) -> list[EbayAccount]:
        return self.db.query(EbayAccount).filter(EbayAccount.is_active.is_(True), EbayAccount.access_token.isnot(None)).order_by(EbayAccount.account_name.asc()).all()

    def upsert_order(self, values: dict, line_items: list[dict]) -> tuple[SoldPostingOrder, bool, int]:
        order = self.db.query(SoldPostingOrder).filter(
            SoldPostingOrder.ebay_account_id == values['ebay_account_id'],
            SoldPostingOrder.order_id == values['order_id'],
        ).first()
        inserted = order is None
        now = datetime.now(UTC)
        if order is None:
            order = SoldPostingOrder(**values)
            self.db.add(order)
            self.db.flush()
        else:
            for key, value in values.items():
                setattr(order, key, value)
            order.updated_at = now
            self.db.flush()

        inserted_lines = 0
        for item_values in line_items:
            line = self.db.query(SoldPostingLineItem).filter(
                SoldPostingLineItem.ebay_account_id == item_values['ebay_account_id'],
                SoldPostingLineItem.order_id == item_values['order_id'],
                SoldPostingLineItem.line_item_id == item_values['line_item_id'],
            ).first()
            item_values['sold_posting_order_id'] = order.id
            if line is None:
                self.db.add(SoldPostingLineItem(**item_values))
                inserted_lines += 1
            else:
                for key, value in item_values.items():
                    setattr(line, key, value)
                line.updated_at = now
        self.db.flush()
        return order, inserted, inserted_lines

    def resolve_image_url(self, account_id: UUID, *, legacy_item_id: str | None, sku: str | None) -> str | None:
        query = self.db.query(EbayOrderLineItem).filter(EbayOrderLineItem.account_id == account_id, EbayOrderLineItem.image_url.isnot(None))
        if legacy_item_id:
            hit = query.filter(or_(EbayOrderLineItem.item_id == legacy_item_id, EbayOrderLineItem.listing_id == legacy_item_id)).order_by(EbayOrderLineItem.updated_at.desc()).first()
            if hit:
                return hit.image_url
        if sku:
            hit = query.filter(EbayOrderLineItem.sku == sku).order_by(EbayOrderLineItem.updated_at.desc()).first()
            if hit:
                return hit.image_url
            product = self.db.query(ConversationProductContext).filter(ConversationProductContext.sku == sku, ConversationProductContext.image_url.isnot(None)).order_by(ConversationProductContext.updated_at.desc()).first()
            if product:
                return product.image_url
        if legacy_item_id:
            product = self.db.query(ConversationProductContext).filter(ConversationProductContext.reference_id == legacy_item_id, ConversationProductContext.image_url.isnot(None)).order_by(ConversationProductContext.updated_at.desc()).first()
            if product:
                return product.image_url
        return None

    def query_rows(self, filters: dict):
        query = self.db.query(SoldPostingLineItem, SoldPostingOrder, EbayAccount).join(SoldPostingOrder, SoldPostingLineItem.sold_posting_order_id == SoldPostingOrder.id).join(EbayAccount, SoldPostingOrder.ebay_account_id == EbayAccount.id)
        if filters.get('date_sold_from'):
            query = query.filter(SoldPostingOrder.creation_date >= _date_start(filters['date_sold_from']))
        if filters.get('date_sold_to'):
            query = query.filter(SoldPostingOrder.creation_date <= _date_end(filters['date_sold_to']))
        if filters.get('date_paid_from'):
            query = query.filter(SoldPostingOrder.payment_date >= _date_start(filters['date_paid_from']))
        if filters.get('date_paid_to'):
            query = query.filter(SoldPostingOrder.payment_date <= _date_end(filters['date_paid_to']))
        if filters.get('account_ids'):
            query = query.filter(SoldPostingOrder.ebay_account_id.in_(filters['account_ids']))
        if filters.get('statuses'):
            query = query.filter(SoldPostingOrder.normalized_status.in_(filters['statuses']))
        if filters.get('sku'):
            query = query.filter(SoldPostingLineItem.sku.ilike(f"%{filters['sku']}%"))
        if filters.get('order_id'):
            query = query.filter(SoldPostingOrder.order_id.ilike(f"%{filters['order_id']}%"))
        if filters.get('buyer_username'):
            query = query.filter(SoldPostingOrder.buyer_username.ilike(f"%{filters['buyer_username']}%"))
        if filters.get('item_id'):
            query = query.filter(SoldPostingLineItem.legacy_item_id.ilike(f"%{filters['item_id']}%"))
        if filters.get('search'):
            term = f"%{filters['search']}%"
            query = query.filter(or_(
                SoldPostingOrder.order_id.ilike(term),
                SoldPostingOrder.legacy_order_id.ilike(term),
                SoldPostingOrder.sales_record_reference.ilike(term),
                SoldPostingLineItem.sku.ilike(term),
                SoldPostingLineItem.legacy_item_id.ilike(term),
                SoldPostingLineItem.title.ilike(term),
                SoldPostingOrder.buyer_username.ilike(term),
                EbayAccount.account_name.ilike(term),
                EbayAccount.ebay_username.ilike(term),
            ))
        return query

    def summary(self, query) -> dict:
        rows = query.all()
        order_ids = {order.id for _, order, _ in rows}
        return {
            'order_count': len(order_ids),
            'line_item_count': len(rows),
            'quantity_sold': sum((line.quantity or 0) for line, _, _ in rows),
            'awaiting_shipment': sum(1 for _, order, _ in rows if order.normalized_status.value == 'AWAITING_SHIPMENT'),
            'shipped': sum(1 for _, order, _ in rows if order.normalized_status.value == 'SHIPPED'),
        }

    def get_order_detail(self, order_id: str) -> SoldPostingOrder | None:
        return self.db.query(SoldPostingOrder).options(joinedload(SoldPostingOrder.line_items), joinedload(SoldPostingOrder.account)).filter(SoldPostingOrder.order_id == order_id).first()


def _date_start(value: date) -> datetime:
    return datetime.combine(value, time.min, tzinfo=UTC)


def _date_end(value: date) -> datetime:
    return datetime.combine(value, time.max, tzinfo=UTC)
