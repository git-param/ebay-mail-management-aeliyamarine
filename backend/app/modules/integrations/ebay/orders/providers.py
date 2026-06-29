from dataclasses import dataclass
from typing import Protocol

from app.modules.integrations.ebay.client.ebay_auth_client import EbayAuthClient


@dataclass(frozen=True)
class OrderPage:
    orders: list[dict]
    total: int | None
    has_more: bool
    status_code: int
    error: object | None = None


class OrderProvider(Protocol):
    def fetch_page(
        self,
        access_token: str,
        *,
        limit: int,
        offset: int,
        filter_value: str | None,
    ) -> OrderPage: ...


class FulfillmentOrderProvider:
    """Order provider backed by Fulfillment API getOrders."""

    def __init__(self, client: EbayAuthClient):
        self.client = client

    def fetch_page(
        self,
        access_token: str,
        *,
        limit: int,
        offset: int,
        filter_value: str | None,
    ) -> OrderPage:
        response = self.client.get_orders_raw(
            access_token,
            limit=limit,
            offset=offset,
            filter_value=filter_value,
        )
        if not response.ok or not isinstance(response.payload, dict):
            return OrderPage([], None, False, response.status_code, response.payload)
        raw_orders = response.payload.get('orders') or []
        orders = [order for order in raw_orders if isinstance(order, dict)]
        total = self._integer(response.payload.get('total'))
        has_more = bool(response.payload.get('next')) or (total is not None and offset + len(orders) < total)
        return OrderPage(orders, total, has_more, response.status_code)

    @staticmethod
    def _integer(value: object) -> int | None:
        try:
            return int(value) if value is not None else None
        except (TypeError, ValueError):
            return None
