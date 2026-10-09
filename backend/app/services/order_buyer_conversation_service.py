"""Resolve the buyer and seller account for a Sold Posting conversation link."""

from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.conversation import Conversation, ConversationStatus
from app.modules.sold_posting.models import SoldPostingOrder


class OrderBuyerConversationService:
    def __init__(self, db: Session):
        self.db = db

    def get_order(self, order_id: str, account_id: UUID) -> SoldPostingOrder:
        order = self.db.scalar(select(SoldPostingOrder).where(
            SoldPostingOrder.order_id == order_id,
            SoldPostingOrder.ebay_account_id == account_id,
        ))
        if not order:
            raise HTTPException(status_code=404, detail='Order not found for this eBay account.')
        if not (order.buyer_username or '').strip():
            raise HTTPException(status_code=422, detail='The buyer eBay username is unavailable for this order.')
        return order

    def resolve(self, order_id: str, account_id: UUID) -> dict:
        order = self.get_order(order_id, account_id)
        buyer = order.buyer_username.strip()
        conversation = self.db.scalar(
            select(Conversation).where(
                Conversation.provider == 'EBAY',
                Conversation.provider_account_id == order.ebay_account_id,
                func.lower(Conversation.buyer_identifier) == buyer.lower(),
                Conversation.provider_conversation_type == 'FROM_MEMBERS',
                Conversation.status != ConversationStatus.CLOSED,
            ).order_by(Conversation.last_message_at.desc().nullslast()).limit(1)
        )
        return {
            'order_id': order.order_id,
            'account_id': order.ebay_account_id,
            'account_name': order.ebay_account_name,
            'buyer_username': buyer,
            'conversation_id': conversation.id if conversation else None,
        }
