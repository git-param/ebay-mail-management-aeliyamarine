from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.models.conversation import Conversation
from app.models.order_context import EbayOrder
from app.repositories.order_context_repository import OrderContextRepository


class OrderContextService:
    def __init__(self, db: Session):
        self.db = db
        self.repository = OrderContextRepository(db)

    def context_for_conversation(self, conversation: Conversation) -> dict:
        selected_order = self._selected_or_direct_order(conversation)
        candidates = [] if selected_order else self._candidate_orders(conversation)
        return {
            'selected_order': selected_order,
            'candidate_orders': candidates,
            'linking': {
                'strategy': self._linking_strategy(conversation, selected_order, candidates),
                'requires_manual_selection': not selected_order and len(candidates) > 1,
            },
            'deep_links': {
                'messages': 'https://my.ebay.com/ws/eBayISAPI.dll?MyMessages&FolderId=0',
            },
        }

    def select_order(self, conversation: Conversation, order_record_id: UUID | None) -> Conversation:
        if order_record_id is None:
            conversation.linked_order_record_id = None
            self.db.commit()
            self.db.refresh(conversation)
            return conversation

        order = self.repository.get_order(order_record_id)
        if not order:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='Order not found')
        if conversation.provider_account_id != order.account_id:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail='Order belongs to another eBay account')

        conversation.linked_order_record_id = order.id
        self.db.commit()
        self.db.refresh(conversation)
        return conversation

    def upsert_order_payload(self, *, account_id: UUID, payload: dict) -> EbayOrder:
        return self.repository.upsert_order(account_id=account_id, payload=payload)

    def upsert_return_payload(self, *, account_id: UUID, payload: dict):
        return self.repository.upsert_return(account_id=account_id, payload=payload)

    def upsert_cancellation_payload(self, *, account_id: UUID, payload: dict):
        return self.repository.upsert_cancellation(account_id=account_id, payload=payload)

    def _selected_or_direct_order(self, conversation: Conversation) -> EbayOrder | None:
        if conversation.linked_order_record_id:
            order = self.repository.get_order(conversation.linked_order_record_id)
            if order:
                return order
        direct_order_id = self._direct_order_id(conversation)
        if conversation.provider_account_id and direct_order_id:
            return self.repository.get_by_order_id(account_id=conversation.provider_account_id, order_id=direct_order_id)
        return None

    def _candidate_orders(self, conversation: Conversation) -> list[EbayOrder]:
        if not conversation.provider_account_id:
            return []
        return self.repository.find_candidates(
            account_id=conversation.provider_account_id,
            buyer_username=conversation.buyer_identifier,
            item_id=self._item_id(conversation),
        )

    def _linking_strategy(self, conversation: Conversation, selected_order: EbayOrder | None, candidates: list[EbayOrder]) -> str:
        if conversation.linked_order_record_id and selected_order:
            return 'MANUAL'
        if selected_order and self._direct_order_id(conversation):
            return 'DIRECT_ORDER_ID'
        if len(candidates) == 1:
            return 'BUYER_ITEM_MATCH'
        if len(candidates) > 1:
            return 'MULTIPLE_CANDIDATES'
        return 'NO_MATCH'

    def _direct_order_id(self, conversation: Conversation) -> str | None:
        for payload in self._payloads(conversation):
            value = self._find_key(payload, {'orderId', 'orderID', 'order_id'})
            if value:
                return value
        return None

    def _item_id(self, conversation: Conversation) -> str | None:
        if conversation.reference_type == 'LISTING' and conversation.reference_id:
            return conversation.reference_id
        for payload in self._payloads(conversation):
            value = self._find_key(payload, {'itemId', 'ItemID', 'legacyItemId'})
            if value:
                return value
        return None

    def _payloads(self, conversation: Conversation) -> list[dict]:
        raw_payload = conversation.raw_payload if isinstance(conversation.raw_payload, dict) else {}
        payloads = [raw_payload]
        for key in ('summary', 'detail'):
            value = raw_payload.get(key)
            if isinstance(value, dict):
                payloads.append(value)
        return payloads

    def _find_key(self, payload: dict, keys: set[str]) -> str | None:
        for key, value in payload.items():
            if key in keys and isinstance(value, str) and value.strip():
                return value.strip()
            if isinstance(value, dict):
                nested = self._find_key(value, keys)
                if nested:
                    return nested
            if isinstance(value, list):
                for item in value:
                    if isinstance(item, dict):
                        nested = self._find_key(item, keys)
                        if nested:
                            return nested
        return None
