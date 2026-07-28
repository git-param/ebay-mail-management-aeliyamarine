from datetime import date, datetime
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel


class SoldPostingRow(BaseModel):
    id: UUID
    order_id: str
    ebay_account_id: UUID
    ebay_account_name: str
    status: str
    date_sold: datetime | None = None
    date_paid: datetime | None = None
    legacy_order_id: str | None = None
    sales_record_reference: str | None = None
    sku: str | None = None
    item_id: str | None = None
    product: str | None = None
    condition: str | None = None
    buyer_username: str | None = None
    quantity: int | None = None
    item_price: Decimal | None = None
    shipping: Decimal | None = None
    total: Decimal | None = None
    currency: str | None = None
    tracking_number: str | None = None
    shipping_carrier_code: str | None = None
    shipping_service_code: str | None = None
    ship_by_date: datetime | None = None
    order_payment_status: str | None = None
    order_fulfillment_status: str | None = None
    image_url: str | None = None
    is_copied: bool = False
    copied_at: datetime | None = None
    copy_count: int = 0
    seller_hub_url: str | None = None


class SoldPostingListSummary(BaseModel):
    order_count: int = 0
    line_item_count: int = 0
    quantity_sold: int = 0
    awaiting_shipment: int = 0
    shipped: int = 0


class SoldPostingSyncInfo(BaseModel):
    last_successful_sync_at: datetime | None = None
    is_running: bool = False


class SoldPostingListResponse(BaseModel):
    items: list[SoldPostingRow]
    page: int
    page_size: int
    total: int
    summary: SoldPostingListSummary
    sync: SoldPostingSyncInfo


class SoldPostingLineItemResponse(BaseModel):
    id: UUID
    line_item_id: str
    sku: str | None = None
    legacy_item_id: str | None = None
    title: str | None = None
    condition: str | None = None
    quantity: int | None = None
    sold_format: str | None = None
    line_item_fulfillment_status: str | None = None
    unit_price: Decimal | None = None
    discount_amount: Decimal | None = None
    line_item_total: Decimal | None = None
    currency: str | None = None
    ship_by_date: datetime | None = None
    image_url: str | None = None
    copied_at: datetime | None = None
    copy_count: int = 0

    class Config:
        from_attributes = True


class SoldPostingOrderDetail(BaseModel):
    id: UUID
    order_id: str
    legacy_order_id: str | None = None
    sales_record_reference: str | None = None
    ebay_account_id: UUID
    ebay_account_name: str
    seller_id: str | None = None
    buyer_username: str | None = None
    creation_date: datetime | None = None
    last_modified_date: datetime | None = None
    payment_date: datetime | None = None
    order_payment_status: str | None = None
    order_fulfillment_status: str | None = None
    normalized_status: str
    cancel_state: str | None = None
    currency: str | None = None
    order_total: Decimal | None = None
    total_due_seller: Decimal | None = None
    shipping_carrier_code: str | None = None
    shipping_service_code: str | None = None
    tracking_number: str | None = None
    ship_by_date: datetime | None = None
    line_items: list[SoldPostingLineItemResponse]

    class Config:
        from_attributes = True


class SoldPostingAccountSyncResult(BaseModel):
    account_id: UUID
    account_name: str
    success: bool
    pages_fetched: int = 0
    orders_received: int = 0
    orders_inserted: int = 0
    orders_updated: int = 0
    line_items_inserted: int = 0
    error_message: str | None = None


class SoldPostingSyncResponse(BaseModel):
    started_at: datetime
    completed_at: datetime
    is_running: bool
    results: list[SoldPostingAccountSyncResult]


class SoldPostingFilterOptions(BaseModel):
    accounts: list[dict]
    statuses: list[str]


class SoldPostingEditRequest(BaseModel):
    status: str | None = None
    sku: str | None = None
    condition: str | None = None
    title: str | None = None
    quantity: int | None = None
    tracking_number: str | None = None
    shipping_carrier_code: str | None = None
    shipping_service_code: str | None = None
    ship_by_date: datetime | None = None
    order_payment_status: str | None = None
    order_fulfillment_status: str | None = None
    buyer_username: str | None = None
