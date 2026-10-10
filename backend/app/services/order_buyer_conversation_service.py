"""Resolve the buyer and seller account for a Sold Posting conversation link."""

from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.conversation import Conversation, ConversationStatus
from app.modules.sold_posting.models import SoldPostingOrder
from app.services.order_context_service import OrderContextService


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
        if conversation:
            self.attach_order(conversation, order)
            self.db.commit()
        return {
            'order_id': order.order_id,
            'account_id': order.ebay_account_id,
            'account_name': order.ebay_account_name,
            'buyer_username': buyer,
            'conversation_id': conversation.id if conversation else None,
        }

    def attach_order(self, conversation: Conversation, sold_order: SoldPostingOrder) -> None:
        """Bridge the exact Sold Posting order into persistent conversation context."""
        if (conversation.provider_account_id != sold_order.ebay_account_id
                or (conversation.buyer_identifier or '').strip().casefold()
                != (sold_order.buyer_username or '').strip().casefold()):
            raise HTTPException(status_code=400, detail='Order does not belong to this conversation buyer and account.')
        service = OrderContextService(self.db)
        order = service.repository.get_by_order_id(
            account_id=sold_order.ebay_account_id, order_id=sold_order.order_id,
        )
        if not order:
            payload = dict(sold_order.raw_payload_json or {})
            payload['orderId'] = sold_order.order_id
            payload['paymentStatus'] = payload.get('orderPaymentStatus') or sold_order.order_payment_status
            payload['fulfillmentStatus'] = payload.get('orderFulfillmentStatus') or sold_order.order_fulfillment_status
            payload['buyer'] = {**(payload.get('buyer') or {}), 'username': sold_order.buyer_username.strip()}
            # Keep provider contact/payment data and enrich missing listing fields.
            raw_items = payload.get('lineItems') or []
            items = []
            for item in sold_order.line_items:
                raw = next((entry for entry in raw_items
                            if isinstance(entry, dict) and entry.get('lineItemId') == item.line_item_id), {})
                raw = {**(item.raw_payload_json or {}), **raw}
                raw.update({
                    'lineItemId': item.line_item_id, 'legacyItemId': item.legacy_item_id,
                    'sku': item.sku, 'title': item.title, 'quantity': item.quantity,
                    'imageUrl': item.image_url,
                })
                if not raw.get('lineItemCost') and item.line_item_cost is not None:
                    raw['lineItemCost'] = {'value': str(item.line_item_cost), 'currency': item.currency}
                items.append(raw)
            payload['lineItems'] = items or raw_items
            order = service.upsert_order_payload(account_id=sold_order.ebay_account_id, payload=payload)
            self.db.flush()
        item_id = next((item.legacy_item_id for item in sold_order.line_items if item.legacy_item_id), None)
        if item_id:
            conversation.reference_id = item_id
            conversation.reference_type = 'LISTING'
        mapping = service.link_conversation_context(
            conversation=conversation, fetched_order=order,
            conversation_detail={'orderId': sold_order.order_id, 'itemId': item_id},
            preserve_sold_posting_context=False,
        )
        if mapping:
            mapping.match_strategy = 'SOLD_POSTING'
