from uuid import UUID

from sqlalchemy import and_, or_, select
from sqlalchemy.orm import Session, selectinload

from app.models.order_context import EbayCancellation, EbayOrder, EbayOrderLineItem, EbayReturn


class OrderContextRepository:
    def __init__(self, db: Session):
        self.db = db

    def get_order(self, order_record_id: UUID) -> EbayOrder | None:
        return self.db.scalar(self._order_statement().where(EbayOrder.id == order_record_id))

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
            filters.append(EbayOrder.buyer_username == buyer_username)
        if item_id:
            filters.append(
                EbayOrder.id.in_(
                    select(EbayOrderLineItem.order_record_id)
                    .where(EbayOrderLineItem.account_id == account_id)
                    .where(EbayOrderLineItem.item_id == item_id)
                )
            )

        if len(filters) == 2:
            statement = statement.where(and_(*filters))
        else:
            statement = statement.where(or_(*filters))

        return list(self.db.scalars(statement.order_by(EbayOrder.created_at.desc()).limit(limit)))

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
                    title=self._string(line_item_payload.get('title')),
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
