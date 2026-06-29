from datetime import UTC, datetime, timedelta
from uuid import UUID

from sqlalchemy import and_, func, or_, select
from sqlalchemy.orm import Session, selectinload

from app.models.order_context import ConversationOrderContext, EbayCancellation, EbayOrder, EbayOrderLineItem, EbayReturn


class OrderContextRepository:
    def __init__(self, db: Session):
        self.db = db

    def get_order(self, order_record_id: UUID) -> EbayOrder | None:
        return self.db.scalar(self._order_statement().where(EbayOrder.id == order_record_id))

    def get_mapping(self, conversation_id: UUID) -> ConversationOrderContext | None:
        return self.db.scalar(
            select(ConversationOrderContext)
            .where(ConversationOrderContext.conversation_id == conversation_id)
        )

    def get_by_order_id(self, *, account_id: UUID, order_id: str) -> EbayOrder | None:
        return self.db.scalar(
            self._order_statement()
            .where(EbayOrder.account_id == account_id)
            .where(EbayOrder.order_id == order_id)
        )

    def find_candidates(
        self,
        *,
        account_id: UUID,
        buyer_username: str | None,
        item_id: str | None,
        limit: int = 10,
    ) -> list[EbayOrder]:
        if not buyer_username and not item_id:
            return []

        statement = self._order_statement().where(EbayOrder.account_id == account_id)
        filters = []
        if buyer_username:
            filters.append(func.lower(EbayOrder.buyer_username) == buyer_username.casefold())
        if item_id:
            filters.append(
                EbayOrder.id.in_(
                    select(EbayOrderLineItem.order_record_id)
                    .where(EbayOrderLineItem.account_id == account_id)
                    .where(or_(EbayOrderLineItem.item_id == item_id, EbayOrderLineItem.listing_id == item_id))
                )
            )

        if len(filters) == 2:
            statement = statement.where(and_(*filters))
        else:
            statement = statement.where(or_(*filters))

        return list(self.db.scalars(statement.order_by(EbayOrder.external_created_at.desc().nullslast(), EbayOrder.order_id.asc()).limit(limit)))

    def find_nearby_buyer_orders(
        self,
        *,
        account_id: UUID,
        buyer_username: str | None,
        activity_at,
        limit: int = 5,
    ) -> list[EbayOrder]:
        if not buyer_username:
            return []

        statement = self._order_statement().where(EbayOrder.account_id == account_id).where(
            func.lower(EbayOrder.buyer_username) == buyer_username.casefold()
        )
        if activity_at:
            window_start = activity_at - timedelta(days=45)
            window_end = activity_at + timedelta(days=7)
            statement = statement.where(EbayOrder.external_created_at >= window_start).where(EbayOrder.external_created_at <= window_end)
        return list(self.db.scalars(statement.order_by(EbayOrder.external_created_at.desc().nullslast(), EbayOrder.order_id.asc()).limit(limit)))

    def upsert_mapping(
        self,
        *,
        conversation_id: UUID,
        identifiers: dict,
        order: EbayOrder | None,
        line_item: EbayOrderLineItem | None,
        buyer_username: str | None,
        match_strategy: str,
        confidence_score: float | None,
    ) -> ConversationOrderContext:
        mapping = self.get_mapping(conversation_id)
        if not mapping:
            mapping = ConversationOrderContext(conversation_id=conversation_id)
            self.db.add(mapping)

        mapping.order_record_id = order.id if order else None
        mapping.ebay_order_id = self._string(identifiers.get('order_id')) or (order.order_id if order else None)
        mapping.legacy_order_id = self._string(identifiers.get('legacy_order_id'))
        mapping.ebay_item_id = self._string(identifiers.get('item_id')) or (line_item.item_id if line_item else None)
        mapping.listing_id = self._string(identifiers.get('listing_id')) or (line_item.listing_id if line_item else None)
        mapping.transaction_id = self._string(identifiers.get('transaction_id'))
        mapping.external_message_id = self._string(identifiers.get('external_message_id'))
        mapping.sku = self._string(identifiers.get('sku')) or (line_item.sku if line_item else None)
        mapping.title = line_item.title if line_item else self._string(identifiers.get('title'))
        mapping.image_url = line_item.image_url if line_item else self._string(identifiers.get('image_url'))
        mapping.buyer_username = buyer_username or (order.buyer_username if order else None)
        mapping.inventory_id = mapping.sku
        mapping.match_strategy = match_strategy
        mapping.confidence_score = confidence_score
        mapping.raw_identifiers = identifiers
        mapping.sync_timestamp = datetime.now(UTC)
        return mapping

    def upsert_order(self, *, account_id: UUID, payload: dict) -> EbayOrder:
        order_id = self._string(payload.get('orderId') or payload.get('order_id'))
        if not order_id:
            raise ValueError('Order payload missing orderId')

        order = self.get_by_order_id(account_id=account_id, order_id=order_id)
        if not order:
            order = EbayOrder(account_id=account_id, order_id=order_id)
            self.db.add(order)

        buyer = payload.get('buyer') if isinstance(payload.get('buyer'), dict) else {}
        order.buyer_username = self._string(buyer.get('username') or payload.get('buyerUsername'))
        order.payment_status = self._string(payload.get('paymentStatus'))
        order.fulfillment_status = self._string(payload.get('fulfillmentStatus'))
        order.cancel_status = self._string(payload.get('cancelStatus'))
        order.pricing_summary = payload.get('pricingSummary') if isinstance(payload.get('pricingSummary'), dict) else None
        refunds = payload.get('refunds')
        order.refunds = refunds if isinstance(refunds, list) else None
        order.refund_status = 'REFUNDED' if order.refunds else None
        order.raw_payload = payload
        order.external_created_at = (
            self._datetime(payload.get('creationDate') or payload.get('createdDate'))
            or order.external_created_at
        )
        order.external_last_modified_at = (
            self._datetime(payload.get('lastModifiedDate'))
            or order.external_last_modified_at
        )

        order.line_items.clear()
        self.db.flush()
        for index, line_item_payload in enumerate(payload.get('lineItems') or [], start=1):
            if not isinstance(line_item_payload, dict):
                continue
            line_item_id = self._string(line_item_payload.get('lineItemId')) or f'{order_id}:{index}'
            price = self._price(line_item_payload)
            order.line_items.append(
                EbayOrderLineItem(
                    account_id=account_id,
                    order_id=order_id,
                    line_item_id=line_item_id,
                    item_id=self._string(line_item_payload.get('itemId') or line_item_payload.get('legacyItemId')),
                    listing_id=self._string(line_item_payload.get('listingId') or line_item_payload.get('legacyListingId')),
                    sku=self._string(line_item_payload.get('sku') or line_item_payload.get('sellerSku')),
                    title=self._string(line_item_payload.get('title')),
                    image_url=self._image_url(line_item_payload),
                    quantity=self._int(line_item_payload.get('quantity')),
                    price_value=price[0],
                    price_currency=price[1],
                    raw_payload=line_item_payload,
                )
            )
        return order

    def upsert_return(self, *, account_id: UUID, payload: dict) -> EbayReturn:
        return_id = self._string(payload.get('returnId') or payload.get('return_id'))
        if not return_id:
            raise ValueError('Return payload missing returnId')

        existing = self.db.scalar(
            select(EbayReturn).where(EbayReturn.account_id == account_id).where(EbayReturn.return_id == return_id)
        )
        item = existing or EbayReturn(account_id=account_id, return_id=return_id)
        if not existing:
            self.db.add(item)
        item.order_id = self._string(payload.get('orderId'))
        item.return_status = self._string(payload.get('returnStatus'))
        item.return_reason = self._string(payload.get('returnReason'))
        item.return_state = self._string(payload.get('returnState'))
        item.raw_payload = payload
        order = self.get_by_order_id(account_id=account_id, order_id=item.order_id) if item.order_id else None
        item.order_record_id = order.id if order else None
        return item

    def upsert_cancellation(self, *, account_id: UUID, payload: dict) -> EbayCancellation:
        cancel_id = self._string(payload.get('cancelId') or payload.get('cancellationId') or payload.get('cancel_id'))
        if not cancel_id:
            raise ValueError('Cancellation payload missing cancelId')

        existing = self.db.scalar(
            select(EbayCancellation).where(EbayCancellation.account_id == account_id).where(EbayCancellation.cancel_id == cancel_id)
        )
        item = existing or EbayCancellation(account_id=account_id, cancel_id=cancel_id)
        if not existing:
            self.db.add(item)
        item.order_id = self._string(payload.get('orderId'))
        item.cancel_state = self._string(payload.get('cancelState'))
        item.cancel_reason = self._string(payload.get('cancelReason'))
        item.requester = self._string(payload.get('requester'))
        item.raw_payload = payload
        order = self.get_by_order_id(account_id=account_id, order_id=item.order_id) if item.order_id else None
        item.order_record_id = order.id if order else None
        return item

    def _order_statement(self):
        return select(EbayOrder).options(
            selectinload(EbayOrder.line_items),
            selectinload(EbayOrder.returns),
            selectinload(EbayOrder.cancellations),
        )

    def _string(self, value: object) -> str | None:
        return value.strip() if isinstance(value, str) and value.strip() else None

    def _int(self, value: object) -> int | None:
        try:
            return int(value) if value is not None else None
        except (TypeError, ValueError):
            return None

    def _price(self, payload: dict) -> tuple[float | None, str | None]:
        price_payload = payload.get('lineItemCost') or payload.get('total') or payload.get('price')
        if not isinstance(price_payload, dict):
            return None, None
        value = price_payload.get('value')
        try:
            price_value = float(value) if value is not None else None
        except (TypeError, ValueError):
            price_value = None
        return price_value, self._string(price_payload.get('currency'))

    def _image_url(self, payload: dict) -> str | None:
        image = payload.get('image') if isinstance(payload.get('image'), dict) else {}
        return (
            self._string(payload.get('imageUrl'))
            or self._string(payload.get('image_url'))
            or self._string(image.get('imageUrl'))
            or self._string(image.get('url'))
        )

    def _datetime(self, value: object) -> datetime | None:
        if not isinstance(value, str) or not value.strip():
            return None
        try:
            return datetime.fromisoformat(value.strip().replace('Z', '+00:00'))
        except ValueError:
            return None
