from datetime import datetime
from uuid import UUID
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session, aliased, selectinload

from app.models.conversation import Conversation, Message
from app.models.ebay_account import EbayAccount
from app.models.message_type import MessageClassification, MessageType
from app.models.user import User


class MessageTypeRepository:
    def __init__(self, db: Session): self.db = db

    def list(self, include_deleted=False):
        query = select(MessageType).options(selectinload(MessageType.keywords)).order_by(MessageType.display_order, MessageType.name)
        if not include_deleted: query = query.where(MessageType.is_deleted.is_(False))
        return list(self.db.scalars(query))

    def get(self, item_id: UUID): return self.db.get(MessageType, item_id)

    def used(self, item_id: UUID) -> bool:
        return bool(self.db.scalar(select(func.count()).select_from(MessageClassification).where(MessageClassification.message_type_id == item_id)))

    def descendants(self, item_id: UUID) -> set[UUID]:
        found, frontier = set(), {item_id}
        while frontier:
            children = set(self.db.scalars(select(MessageType.id).where(MessageType.parent_id.in_(frontier))))
            children -= found
            found |= children; frontier = children
        return found


class MessageClassificationRepository:
    def __init__(self, db: Session): self.db = db

    def create(self, **values):
        row = MessageClassification(**values); self.db.add(row); self.db.flush(); return row

    def query(self, *, date_from=None, date_to=None, seller_account_id=None, user_id=None,
              category_id=None, subcategory_id=None, conversation_id=None, search=None):
        parent = aliased(MessageType)
        query = (select(MessageClassification, Conversation, Message, EbayAccount, User, MessageType, parent)
                 .join(Conversation, Conversation.id == MessageClassification.conversation_id)
                 .join(Message, Message.id == MessageClassification.conversation_message_id)
                 .outerjoin(EbayAccount, EbayAccount.id == MessageClassification.seller_account_id)
                 .join(User, User.id == MessageClassification.user_id)
                 .join(MessageType, MessageType.id == MessageClassification.message_type_id)
                 .outerjoin(parent, parent.id == MessageType.parent_id))
        if date_from: query = query.where(MessageClassification.created_at >= date_from)
        if date_to: query = query.where(MessageClassification.created_at < date_to)
        if seller_account_id: query = query.where(MessageClassification.seller_account_id == seller_account_id)
        if user_id: query = query.where(MessageClassification.user_id == user_id)
        if category_id: query = query.where(or_(MessageType.id == category_id, MessageType.parent_id == category_id))
        if subcategory_id: query = query.where(MessageType.id == subcategory_id)
        if conversation_id: query = query.where(MessageClassification.conversation_id == conversation_id)
        if search:
            term = f'%{search}%'; query = query.where(or_(Message.body.ilike(term), Conversation.buyer_identifier.ilike(term), User.full_name.ilike(term)))
        return query
