from datetime import UTC, date, datetime
from uuid import UUID

from sqlalchemy import func, or_
from sqlalchemy.orm import Session, joinedload

from app.models.conversation import Conversation
from app.models.ebay_account import EbayAccount
from app.models.offer import Offer
from app.models.order_context import ConversationOrderContext, ConversationProductContext, EbayOrderLineItem
from app.models.user import User
from app.modules.offer_management.models import OfferManagementEntry, OfferManagementEntryHistory, OfferManagementStatus


class OfferManagementRepository:
    def __init__(self, db: Session):
        self.db = db

    def next_entry_number(self) -> int:
        return int(self.db.query(func.coalesce(func.max(OfferManagementEntry.entry_number), 0)).scalar() or 0) + 1

    def create(self, entry: OfferManagementEntry, user_id: UUID) -> OfferManagementEntry:
        self.db.add(entry)
        self.db.flush()
        self.add_history(entry.id, user_id, 'CREATE', None, self.snapshot(entry))
        self.db.commit()
        self.db.refresh(entry)
        return entry

    def get(self, entry_id: UUID) -> OfferManagementEntry | None:
        return (
            self.db.query(OfferManagementEntry)
            .options(joinedload(OfferManagementEntry.created_by), joinedload(OfferManagementEntry.related_conversation))
            .filter(OfferManagementEntry.id == entry_id)
            .first()
        )

    def get_by_listing_id(self, listing_id: str) -> OfferManagementEntry | None:
        return (
            self.db.query(OfferManagementEntry)
            .options(joinedload(OfferManagementEntry.created_by))
            .filter(OfferManagementEntry.listing_id == listing_id)
            .order_by(OfferManagementEntry.created_at.desc())
            .first()
        )

    def update(self, entry: OfferManagementEntry, values: dict, user_id: UUID) -> OfferManagementEntry:
        previous = self.snapshot(entry)
        for key, value in values.items():
            setattr(entry, key, value)
        entry.updated_by_user_id = user_id
        entry.updated_at = datetime.now(UTC)
        self.db.flush()
        current = self.snapshot(entry)
        changed_prev = {k: previous.get(k) for k in values if previous.get(k) != current.get(k)}
        changed_new = {k: current.get(k) for k in values if previous.get(k) != current.get(k)}
        if changed_new:
            self.add_history(entry.id, user_id, 'UPDATE', changed_prev, changed_new)
        self.db.commit()
        self.db.refresh(entry)
        return entry

    def delete(self, entry: OfferManagementEntry) -> None:
        self.db.delete(entry)
        self.db.commit()

    def delete_many(self, entries: list[OfferManagementEntry]) -> int:
        count = len(entries)
        for entry in entries:
            self.db.delete(entry)
        self.db.commit()
        return count

    def add_history(self, entry_id: UUID, user_id: UUID | None, action: str, previous: dict | None, new: dict | None) -> None:
        self.db.add(OfferManagementEntryHistory(
            offer_entry_id=entry_id,
            changed_by_user_id=user_id,
            action=action,
            previous_values=previous,
            new_values=new,
        ))

    def history(self, entry_id: UUID) -> list[OfferManagementEntryHistory]:
        return (
            self.db.query(OfferManagementEntryHistory)
            .filter(OfferManagementEntryHistory.offer_entry_id == entry_id)
            .order_by(OfferManagementEntryHistory.changed_at.desc())
            .all()
        )

    def query_entries(self, filters: dict, user) :
        query = self.db.query(OfferManagementEntry).options(joinedload(OfferManagementEntry.created_by))
        if filters.get('created_by_user_id'):
            query = query.filter(OfferManagementEntry.created_by_user_id == filters['created_by_user_id'])
        if filters.get('from_date'):
            query = query.filter(OfferManagementEntry.offer_date >= filters['from_date'])
        if filters.get('to_date'):
            query = query.filter(OfferManagementEntry.offer_date <= filters['to_date'])
        if filters.get('next_offer_followup'):
            query = query.filter(
                OfferManagementEntry.next_offer_followup
                == filters['next_offer_followup']
            )
        for key in ['ebay_account_id', 'status', 'outcome', 'buyer_id', 'sku', 'listing_id', 'is_high_value', 'currency']:
            value = filters.get(key)
            if value not in (None, ''):
                query = query.filter(getattr(OfferManagementEntry, key) == value)
        if filters.get('search'):
            term = f"%{filters['search']}%"
            query = query.filter(or_(
                OfferManagementEntry.listing_id.ilike(term),
                OfferManagementEntry.sku.ilike(term),
                OfferManagementEntry.buyer_id.ilike(term),
                OfferManagementEntry.product_title.ilike(term),
                OfferManagementEntry.remarks.ilike(term),
            ))
        return query

    def lookup_sources(self, listing_id: str) -> dict:
        offers = (
            self.db.query(Offer)
            .options(joinedload(Offer.account), joinedload(Offer.conversation))
            .filter(Offer.listing_id == listing_id)
            .order_by(Offer.created_at_provider.desc().nullslast(), Offer.created_at.desc())
            .all()
        )
        product = (
            self.db.query(ConversationProductContext)
            .filter(ConversationProductContext.reference_id == listing_id)
            .order_by(ConversationProductContext.updated_at.desc())
            .first()
        )
        order_line = (
            self.db.query(EbayOrderLineItem)
            .filter(or_(EbayOrderLineItem.listing_id == listing_id, EbayOrderLineItem.item_id == listing_id))
            .order_by(EbayOrderLineItem.updated_at.desc())
            .first()
        )
        order_context = (
            self.db.query(ConversationOrderContext)
            .filter(ConversationOrderContext.listing_id == listing_id)
            .order_by(ConversationOrderContext.updated_at.desc())
            .first()
        )
        conversation = None
        if order_context and order_context.conversation_id:
            conversation = self.db.query(Conversation).filter(Conversation.id == order_context.conversation_id).first()
        elif product and product.conversation_id:
            conversation = self.db.query(Conversation).filter(Conversation.id == product.conversation_id).first()
        elif offers and offers[0].conversation_id:
            conversation = offers[0].conversation
        else:
            conversation = (
                self.db.query(Conversation)
                .filter(Conversation.reference_id == listing_id)
                .order_by(Conversation.updated_at.desc())
                .first()
            )
        account = None
        account_id = (
            offers[0].account_id if offers else
            conversation.provider_account_id if conversation and conversation.provider_account_id else
            order_line.account_id if order_line else
            None
        )
        if account_id:
            account = self.db.query(EbayAccount).filter(EbayAccount.id == account_id).first()
        return {'offers': offers, 'product': product, 'order_line': order_line, 'order_context': order_context, 'conversation': conversation, 'account': account}

    def summary(self, query) -> dict:
        today = date.today()
        items = query.all()
        return {
            'total_entries': len(items),
            'open_offers': sum(1 for x in items if x.status not in {
                OfferManagementStatus.CLOSED,
                OfferManagementStatus.SOLD,
                OfferManagementStatus.CANCELLED,
                OfferManagementStatus.CLOSED_PRICE_NOT_MATCHED,
                OfferManagementStatus.CLOSED_NO_RESPONSE,
                OfferManagementStatus.CLOSED_BUYER_PURCHASED_ELSEWHERE,
                OfferManagementStatus.CLOSED_OUT_OF_STOCK,
            }),
            'follow_ups_due': sum(
                1
                for x in items
                if (
                    x.status == OfferManagementStatus.OPEN
                    and x.next_offer_followup
                    and x.next_offer_followup <= today
                )
            ),
            'awaiting_payment': sum(1 for x in items if x.status == OfferManagementStatus.AWAITING_PAYMENT),
            'sold': sum(
                1
                for x in items
                if (
                    x.status == OfferManagementStatus.SOLD
                    or str(x.outcome.value if hasattr(x.outcome, 'value') else x.outcome)
                    == 'SOLD'
                )
            ),
            'high_value_offers': sum(1 for x in items if x.is_high_value),
        }

    @staticmethod
    def snapshot(entry: OfferManagementEntry) -> dict:
        data = {}
        for column in OfferManagementEntry.__table__.columns:
            value = getattr(entry, column.name)
            data[column.name] = str(value) if value is not None else None
        return data
