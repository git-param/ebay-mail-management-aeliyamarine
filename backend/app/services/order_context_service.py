import logging
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.models.conversation import Conversation
from app.models.order_context import ConversationOrderContext, EbayOrder, EbayOrderLineItem
from app.repositories.order_context_repository import OrderContextRepository
from app.schemas.conversation import OrderContextResponse, OrderLinkingResponse, OrderContextOrderResponse, OrderLineItemResponse


logger = logging.getLogger(__name__)


class OrderContextService:
    def __init__(self, db: Session):
        self.db = db
        self.repository = OrderContextRepository(db)

    def context_for_conversation(self, conversation: Conversation) -> dict:
        mapping = self.repository.get_mapping(conversation.id)
        selected_order = self._selected_or_direct_order(conversation)
        candidates = [] if selected_order else self._candidate_orders(conversation)
        return {
            'mapping': mapping,
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

    def link_conversation_context(
        self,
        *,
        conversation: Conversation,
        conversation_summary: dict | None = None,
        conversation_detail: dict | None = None,
        fetched_order: EbayOrder | None = None,
        persist_unmatched: bool = True,
        allow_direct_order_id: bool = True,
    ) -> ConversationOrderContext | None:
        if conversation.id is None:
            self.db.flush()
        identifiers = self.extract_order_identifiers(
            conversation=conversation,
            extra_payloads=[conversation_summary or {}, conversation_detail or {}],
        )
        order_id = identifiers.get('order_id') or identifiers.get('legacy_order_id')
        item_id = identifiers.get('item_id')
        listing_id = identifiers.get('listing_id')
        order = fetched_order
        strategy = 'NO_MATCH'
        confidence = 0.0

        if not order and allow_direct_order_id and conversation.provider_account_id and order_id:
            order = self.repository.get_by_order_id(account_id=conversation.provider_account_id, order_id=order_id)
        if order:
            strategy = 'DIRECT_ORDER_ID'
            confidence = 1.0
        elif conversation.provider_account_id and (item_id or listing_id or conversation.buyer_identifier):
            candidate_item_id = item_id or listing_id or conversation.reference_id

            candidates = self.repository.find_candidates(
                account_id=conversation.provider_account_id,
                buyer_username=conversation.buyer_identifier,
                item_id=candidate_item_id,
                limit=10,
            )

            if len(candidates) == 1:
                order = candidates[0]
                strategy = 'BUYER_ITEM_MATCH'
                confidence = 0.95

            elif len(candidates) > 1:
                order = self._deterministic_best_order(conversation, candidates)
                strategy = 'BUYER_ITEM_DATE_MATCH'
                confidence = 0.85

            else:
                nearby = self.repository.find_nearby_buyer_orders(
                    account_id=conversation.provider_account_id,
                    buyer_username=conversation.buyer_identifier,
                    activity_at=conversation.last_message_at or conversation.external_created_at,
                    limit=2,
                )

                if len(nearby) == 1:
                    order = nearby[0]
                    strategy = 'BUYER_NEARBY_ORDER'
                    confidence = 0.60

                elif len(nearby) > 1:
                    order = self._deterministic_best_order(conversation, nearby)
                    strategy = 'BUYER_NEARBY_DATE_MATCH'
                    confidence = 0.50

        line_item = self._best_line_item(order, item_id=item_id, listing_id=listing_id, sku=identifiers.get('sku')) if order else None
        if order:
            conversation.linked_order_record_id = order.id

        if not order and not persist_unmatched:
            return None

        mapping = self.repository.upsert_mapping(
            conversation_id=conversation.id,
            identifiers=identifiers,
            order=order,
            line_item=line_item,
            buyer_username=conversation.buyer_identifier,
            match_strategy=strategy,
            confidence_score=confidence,
        )
        logger.warning(
            'Conversation order context linked conversation_id=%s order_id=%s item_id=%s strategy=%s confidence=%s',
            conversation.id,
            order.order_id if order else 'not found',
            item_id or listing_id or 'not found',
            strategy,
            confidence,
        )
        return mapping

    def _deterministic_best_order(
        self,
        conversation: Conversation,
        candidates: list[EbayOrder],
    ) -> EbayOrder:
        activity_at = conversation.last_message_at or conversation.external_created_at
        if activity_at:
            return min(
                candidates,
                key=lambda candidate: (
                    abs(((candidate.external_created_at or candidate.created_at) - activity_at).total_seconds()),
                    candidate.order_id,
                ),
            )
        return min(candidates, key=lambda candidate: candidate.order_id)

    def order_context_card(self, conversation: Conversation) -> dict | None:
        mapping = self.repository.get_mapping(conversation.id)

        if not mapping:
            mapping = self.link_conversation_context(conversation=conversation)

        if not mapping or not mapping.order_record_id:
            return None
        return {
            'order_id': mapping.ebay_order_id or '',
            'sku': mapping.sku or '',
            'title': mapping.title or '',
            'image_url': mapping.image_url or '',
            'buyer': mapping.buyer_username or '',
            'inventory_id': mapping.inventory_id or mapping.sku or '',
        }

    def extract_order_identifiers(self, *, conversation: Conversation, extra_payloads: list[dict] | None = None) -> dict:
        payloads = self._payloads(conversation) + [payload for payload in (extra_payloads or []) if isinstance(payload, dict)]
        identifiers = {
            'order_id': self._find_key(payloads, {'orderId', 'orderID', 'order_id'}),
            'legacy_order_id': self._find_key(payloads, {'legacyOrderId', 'legacy_order_id'}),
            'item_id': self._find_key(payloads, {'itemId', 'ItemID', 'legacyItemId', 'ebayItemId'}),
            'listing_id': self._find_key(payloads, {'listingId', 'listing_id', 'legacyListingId'}),
            'transaction_id': self._find_key(payloads, {'transactionId', 'transaction_id'}),
            'external_message_id': self._find_key(payloads, {'externalMessageId', 'external_message_id', 'messageId'}),
            'sku': self._find_key(payloads, {'sku', 'sellerSku', 'SKU'}),
            'title': self._find_key(payloads, {'title', 'itemTitle', 'listingTitle'}),
            'image_url': self._find_key(payloads, {'imageUrl', 'image_url', 'thumbnailImageUrl'}),
        }
        if conversation.reference_type == 'LISTING' and conversation.reference_id:
            identifiers['item_id'] = identifiers.get('item_id') or conversation.reference_id
            identifiers['listing_id'] = identifiers.get('listing_id') or conversation.reference_id
        return {key: value for key, value in identifiers.items() if value}

    def upsert_return_payload(self, *, account_id: UUID, payload: dict):
        return self.repository.upsert_return(account_id=account_id, payload=payload)

    def upsert_cancellation_payload(self, *, account_id: UUID, payload: dict):
        return self.repository.upsert_cancellation(account_id=account_id, payload=payload)

    def _selected_or_direct_order(self, conversation: Conversation) -> EbayOrder | None:
        if conversation.linked_order_record_id:
            order = self.repository.get_order(conversation.linked_order_record_id)
            if order:
                return order
        mapping = self.repository.get_mapping(conversation.id)
        if mapping and mapping.order_record_id:
            order = self.repository.get_order(mapping.order_record_id)
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
        identifiers = self.extract_order_identifiers(conversation=conversation)
        return identifiers.get('order_id') or identifiers.get('legacy_order_id')

    def _item_id(self, conversation: Conversation) -> str | None:
        if conversation.reference_type == 'LISTING' and conversation.reference_id:
            return conversation.reference_id
        return self.extract_order_identifiers(conversation=conversation).get('item_id')

    def _payloads(self, conversation: Conversation) -> list[dict]:
        raw_payload = conversation.raw_payload if isinstance(conversation.raw_payload, dict) else {}
        payloads = [raw_payload]
        for key in ('summary', 'detail'):
            value = raw_payload.get(key)
            if isinstance(value, dict):
                payloads.append(value)
        return payloads

    def _find_key(self, payload: object, keys: set[str]) -> str | None:
        if isinstance(payload, list):
            for item in payload:
                nested = self._find_key(item, keys)
                if nested:
                    return nested
        if isinstance(payload, dict):
            for key, value in payload.items():
                if key in keys and value is not None:
                    text = str(value).strip()
                    if text:
                        return text
                nested = self._find_key(value, keys)
                if nested:
                    return nested
        return None

    def _best_line_item(
        self,
        order: EbayOrder,
        *,
        item_id: str | None,
        listing_id: str | None,
        sku: str | None,
    ) -> EbayOrderLineItem | None:
        for line_item in order.line_items:
            if item_id and line_item.item_id == item_id:
                return line_item
            if listing_id and line_item.listing_id == listing_id:
                return line_item
            if sku and line_item.sku == sku:
                return line_item
        return order.line_items[0] if order.line_items else None

    def serialize_context(self, context):
        if not context:
            return None

        order = context["order"]
        mapping = context["mapping"]

        linking = OrderLinkingResponse(
            strategy=mapping.match_strategy or "unknown",
            requires_manual_selection=False,
        )

        if not order:
            return OrderContextResponse(
                selected_order=None,
                candidate_orders=[],
                linking=linking,
                deep_links={},
            )

        return OrderContextResponse(
            selected_order=OrderContextOrderResponse(
                id=order.id,
                order_id=order.order_id,
                buyer_username=order.buyer_username,
                payment_status=order.payment_status,
                fulfillment_status=order.fulfillment_status,
                cancel_status=order.cancel_status,
                refund_status=order.refund_status,
                pricing_summary=order.pricing_summary,
                refunds=order.refunds,
                line_items=[
                    OrderLineItemResponse(
                        id=li.id,
                        item_id=li.item_id,
                        listing_id=li.listing_id,
                        sku=li.sku,
                        title=li.title,
                        image_url=li.image_url,
                        quantity=li.quantity,
                        price_value=li.price_value,
                        price_currency=li.price_currency,
                    )
                    for li in order.line_items
                ],
                returns=[
                    ReturnContextResponse(
                        id=r.id,
                        return_id=r.return_id,
                        return_status=r.return_status,
                        return_reason=r.return_reason,
                        return_state=r.return_state,
                        created_date=r.created_date,
                        ebay_url=f"https://www.ebay.com/itm/{order.order_id}",
                    )
                    for r in (order.returns or [])
                ],
                cancellations=[
                    CancellationContextResponse(
                        id=c.id,
                        cancel_id=c.cancel_id,
                        cancel_state=c.cancel_state,
                        cancel_reason=c.cancel_reason,
                        requester=c.requester,
                        created_date=None,
                        ebay_url=f"https://www.ebay.com/itm/{order.order_id}",
                    )
                    for c in (order.cancellations or [])
                ],
                ebay_url=f"https://www.ebay.com/itm/{order.order_id}",
            ),

            candidate_orders=[],
            linking=linking,
            deep_links={},
        )
    
    def build_context(self, conversation):
        mapping = self.repository.get_mapping(conversation.id)
        if not mapping:
            return None

        order = None
        if mapping.order_record_id:
            order = self.repository.get_order(mapping.order_record_id)

        return {
            "mapping": mapping,
            "order": order,
        }
