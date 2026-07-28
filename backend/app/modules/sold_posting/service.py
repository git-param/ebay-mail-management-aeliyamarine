"""
Sold Posting Synchronization Service

This module provides the service layer for synchronizing eBay sold orders
(fulfillment orders) into the local database. It handles:
- Fetching orders from eBay API with pagination and retries.
- Incremental sync using last-modified date filters.
- State tracking per eBay account to manage sync progress.
- Concurrent sync prevention via a global flag.
- Mapping eBay payloads to local database models.
"""

import logging
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from time import sleep
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.api.dependencies import is_admin
from app.models.ebay_account import EbayAccount
from app.modules.integrations.ebay.oauth.token_service import EbayTokenService
from app.modules.sold_posting.models import SoldPostingOrder, SoldPostingStatus, SoldPostingSyncState, SoldPostingSyncStatus
from app.modules.sold_posting.repository import SoldPostingRepository
from app.modules.sold_posting.status import normalize_sold_posting_status

logger = logging.getLogger(__name__)

# Global flag to prevent multiple sync runs concurrently.
# In a distributed environment this should be replaced with a distributed lock.
_sync_running = False


@dataclass
class AccountSyncResult:
    """Result summary for a single eBay account sync attempt."""

    account_id: UUID
    account_name: str
    success: bool
    pages_fetched: int = 0
    orders_received: int = 0
    orders_inserted: int = 0
    orders_updated: int = 0
    line_items_inserted: int = 0
    error_message: str | None = None


class SoldPostingService:
    """
    Service for synchronizing and querying eBay sold posting orders.
    """

    # Maximum number of orders per API request.
    PAGE_SIZE = 200
    # Safety limit to avoid infinite loops in case of API pagination issues.
    MAX_PAGES = 1000
    # Number of retries for transient API errors.
    MAX_RETRIES = 3
    # Initial sync window (last 90 days) when no prior sync exists.
    INITIAL_WINDOW = timedelta(days=90)
    # Overlap added to the filter start to avoid missing orders updated
    # during the sync process (eventual consistency).
    CURSOR_OVERLAP = timedelta(minutes=7)
    # Safety buffer to avoid eBay API rejecting requests with an end timestamp
    # that is even slightly in the future due to clock skew.
    EBAY_CLOCK_SAFETY_DELAY = timedelta(minutes=10)

    def __init__(self, db: Session):
        self.db = db
        self.repo = SoldPostingRepository(db)
        self.token_service = EbayTokenService(db)

    def assert_admin_can_sync(self, user) -> None:
        """Raise HTTP 403 if the user is not an admin."""
        if not is_admin(user):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Only admins can start Sold Posting synchronization",
            )

    def sync_all_accounts(self) -> dict:
        """
        Trigger synchronization for all active eBay accounts.

        Returns a summary of the sync run, including per-account results.
        Raises HTTP 409 if a sync is already in progress.
        """
        global _sync_running
        if _sync_running:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Synchronization already in progress",
            )
        _sync_running = True
        started_at = datetime.now(UTC)
        results = []
        try:
            for account in self.repo.active_accounts():
                results.append(self.sync_account(account))
            completed_at = datetime.now(UTC)
            return {
                "started_at": started_at,
                "completed_at": completed_at,
                "is_running": False,
                "results": [r.__dict__ for r in results],
            }
        finally:
            _sync_running = False

    def sync_account(self, account: EbayAccount) -> AccountSyncResult:
        """
        Perform a full sync for a single eBay account.

        Fetches orders using a time‑based filter (creation or last‑modified date)
        and upserts them into the local database. Updates sync state on success/failure.
        """
        # Retrieve or create the sync state record for this account.
        state = self.repo.get_or_create_sync_state(account.id)
        state.last_attempted_sync_at = datetime.now(UTC)
        state.sync_status = SoldPostingSyncStatus.RUNNING
        state.error_message = None
        self.db.commit()

        result = AccountSyncResult(account.id, account.account_name or account.ebay_username, True)

        # eBay API rejects filters with an end time that is even slightly in the future.
        # Subtract a safety margin to guarantee the timestamp is in the past.
        synced_through = datetime.now(UTC) - self.EBAY_CLOCK_SAFETY_DELAY
        filter_value = self._filter_for_state(state, synced_through)

        offset = 0
        try:
            while result.pages_fetched < self.MAX_PAGES:
                page = self._fetch_page(account, offset, filter_value)
                orders = page.get("orders") or []
                result.pages_fetched += 1
                result.orders_received += len(orders)

                for payload in orders:
                    # Each order is upserted in a nested transaction so that
                    # a single failure does not roll back the entire page.
                    with self.db.begin_nested():
                        order_values, line_values = self._map_order(account, payload)
                        _, inserted, inserted_lines = self.repo.upsert_order(order_values, line_values)
                        result.orders_inserted += 1 if inserted else 0
                        result.orders_updated += 0 if inserted else 1
                        result.line_items_inserted += inserted_lines

                total = int(page.get("total") or 0)
                # Stop if there are no more orders or we have reached the total.
                if not orders or offset + len(orders) >= total:
                    break
                offset += len(orders)

            # Mark sync as successful and update state.
            state.initial_sync_completed = True
            state.last_successful_sync_at = synced_through
            state.sync_status = SoldPostingSyncStatus.SUCCESS
            self._apply_state_counts(state, result)
            self.db.commit()
            return result

        except Exception as exc:
            # On failure, rollback and update state with error details.
            self.db.rollback()
            state = self.repo.get_or_create_sync_state(account.id)
            state.sync_status = SoldPostingSyncStatus.FAILED
            state.error_message = str(exc)[:1000]
            self._apply_state_counts(state, result)
            self.db.commit()
            logger.exception("Sold Posting sync failed account_id=%s", account.id)
            result.success = False
            result.error_message = str(exc)
            return result

    def list_rows(self, filters: dict, page: int, page_size: int, sort_by: str, sort_direction: str) -> dict:
        """
        Return a paginated, filtered, and sorted list of sold orders for the UI.

        Also includes a summary (counts, totals) and sync status information.
        """
        query = self.repo.query_rows(filters)
        total = query.count()
        summary = self.repo.summary(query)

        # Map sort field names to SQLAlchemy model columns.
        sort_map = {
            "date_sold": SoldPostingOrder.creation_date,
            "date_paid": SoldPostingOrder.payment_date,
            "total": SoldPostingOrder.order_total,
        }
        sort_col = sort_map.get(sort_by, SoldPostingOrder.creation_date)
        if sort_direction == "asc":
            query = query.order_by(sort_col.asc().nullslast())
        else:
            query = query.order_by(sort_col.desc().nullslast())

        rows = query.offset((page - 1) * page_size).limit(page_size).all()

        return {
            "items": [self._row(line, order, account) for line, order, account in rows],
            "page": page,
            "page_size": page_size,
            "total": total,
            "summary": summary,
            "sync": self.sync_info(),
        }

    def sync_info(self) -> dict:
        """Return basic information about the last sync and whether a sync is running."""
        last_success = self.db.query(SoldPostingSyncState.last_successful_sync_at).order_by(SoldPostingSyncState.last_successful_sync_at.desc().nullslast()).limit(1).scalar()
        return {"last_successful_sync_at": last_success, "is_running": _sync_running}

    def detail(self, order_id: str):
        """Return detailed data for a single order by its local order ID."""
        order = self.repo.get_order_detail(order_id)
        if not order:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Sold Posting order not found",
            )
        return order

    # -------------------------------------------------------------------------
    # Private helpers
    # -------------------------------------------------------------------------

    def _fetch_page(self, account: EbayAccount, offset: int, filter_value: str) -> dict:
        """
        Fetch one page of orders from the eBay API with retries.

        Handles token refresh on 401, retries on rate limits (429) and server errors.
        """
        refreshed = False
        for attempt in range(1, self.MAX_RETRIES + 1):
            response = self.token_service.client.get_orders_raw(
                account.access_token,
                limit=self.PAGE_SIZE,
                offset=offset,
                filter_value=filter_value,
            )

            # Access token expired – refresh and retry once.
            if response.status_code == 401 and not refreshed:
                account = self.token_service.refresh_access_token(account.id)
                refreshed = True
                continue

            # Rate limit or server error – wait and retry.
            if response.status_code == 429 or response.status_code >= 500:
                retry_after = None
                if response.response_headers:
                    retry_after = response.response_headers.get("Retry-After")
                if attempt < self.MAX_RETRIES:
                    # Use Retry-After header if present, otherwise exponential backoff.
                    wait = int(retry_after) if retry_after and retry_after.isdigit() else min(2 ** (attempt - 1), 8)
                    sleep(wait)
                    continue

            # Any other non‑OK response is considered fatal.
            if not response.ok or not isinstance(response.payload, dict):
                raise RuntimeError(f"eBay fulfillment order request failed with status {response.status_code}")

            return response.payload

        raise RuntimeError("eBay fulfillment order request failed after retries")

    def _filter_for_state(self, state, end: datetime) -> str:
        """
        Build the eBay API filter string based on the sync state.

        - If initial sync is not complete, use `creationdate` over the last 90 days.
        - Otherwise, use `lastmodifieddate` from last successful sync (with overlap)
          up to the safe end timestamp.
        """
        end = end.astimezone(UTC)

        if state.initial_sync_completed and state.last_successful_sync_at:
            start = state.last_successful_sync_at.astimezone(UTC) - self.CURSOR_OVERLAP

            # Guard against a stale cursor that might be ahead of the safe end time.
            if start >= end:
                start = end - self.CURSOR_OVERLAP

            return f"lastmodifieddate:[{self._ebay_datetime(start)}..{self._ebay_datetime(end)}]"

        # First‑time sync: fetch orders created in the last 90 days.
        start = end - self.INITIAL_WINDOW
        return f"creationdate:[{self._ebay_datetime(start)}..{self._ebay_datetime(end)}]"

    def _map_order(self, account: EbayAccount, payload: dict) -> tuple[dict, list[dict]]:
        """
        Convert an eBay order payload into a dict of order fields and a list of line item dicts.

        The returned values are ready for `repo.upsert_order()`.
        """
        pricing = payload.get("pricingSummary") or {}
        payment = payload.get("paymentSummary") or {}
        cancel = payload.get("cancelStatus") or {}
        instructions = payload.get("fulfillmentStartInstructions") or []
        ship = instructions[0] if instructions else {}
        line_items = payload.get("lineItems") or []
        currency = self._money(pricing.get("total"))[1]
        status_value = normalize_sold_posting_status(payload)

        # Order-level fields.
        order_values = {
            "ebay_account_id": account.id,
            "ebay_account_name": account.account_name or account.store_name or account.ebay_username,
            "order_id": str(payload.get("orderId")),
            "legacy_order_id": payload.get("legacyOrderId"),
            "sales_record_reference": payload.get("salesRecordReference"),
            "seller_id": payload.get("sellerId"),
            "buyer_username": (payload.get("buyer") or {}).get("username"),
            "creation_date": self._dt(payload.get("creationDate")),
            "last_modified_date": self._dt(payload.get("lastModifiedDate")),
            "payment_date": self._payment_date(payment.get("payments") or []),
            "order_payment_status": payload.get("orderPaymentStatus"),
            "order_fulfillment_status": payload.get("orderFulfillmentStatus"),
            "normalized_status": status_value,
            "cancel_state": cancel.get("cancelState"),
            "currency": currency,
            "price_subtotal": self._money(pricing.get("priceSubtotal"))[0],
            "delivery_cost": self._money(pricing.get("deliveryCost"))[0],
            "discount_total": sum(
                v
                for v in [
                    self._money(pricing.get("deliveryDiscount"))[0],
                    self._money(pricing.get("priceDiscount"))[0],
                ]
                if v is not None
            ),
            "tax_total": self._money(pricing.get("tax"))[0],
            "order_total": self._money(pricing.get("total"))[0],
            "total_due_seller": self._money(payment.get("totalDueSeller"))[0],
            "total_marketplace_fee": self._money(payload.get("totalMarketplaceFee"))[0],
            "listing_marketplace_ids": list({x.get("listingMarketplaceId") for x in line_items if x.get("listingMarketplaceId")}),
            "purchase_marketplace_ids": list({x.get("purchaseMarketplaceId") for x in line_items if x.get("purchaseMarketplaceId")}),
            "shipping_carrier_code": ship.get("shippingCarrierCode"),
            "shipping_service_code": ship.get("shippingServiceCode"),
            "tracking_number": ((ship.get("shippingStep") or {}).get("shipTo") or {}).get("trackingNumber")
            or (ship.get("shippingStep") or {}).get("trackingNumber"),
            "ship_by_date": self._dt(ship.get("shipByDate")),
            "min_estimated_delivery_date": self._dt(ship.get("minEstimatedDeliveryDate")),
            "max_estimated_delivery_date": self._dt(ship.get("maxEstimatedDeliveryDate")),
            "raw_payload_json": payload,
        }

        # Line‑item fields.
        mapped_lines = []
        for item in line_items:
            item_currency = self._money(item.get("total") or item.get("lineItemCost"))[1] or currency
            legacy_item_id = item.get("legacyItemId")
            sku = item.get("sku") or None
            mapped_lines.append(
                {
                    "ebay_account_id": account.id,
                    "order_id": order_values["order_id"],
                    "line_item_id": str(item.get("lineItemId")),
                    "legacy_item_id": legacy_item_id,
                    "legacy_variation_id": item.get("legacyVariationId"),
                    "sku": sku,
                    "title": item.get("title"),
                    "quantity": item.get("quantity"),
                    "sold_format": item.get("soldFormat"),
                    "line_item_fulfillment_status": item.get("lineItemFulfillmentStatus"),
                    "listing_marketplace_id": item.get("listingMarketplaceId"),
                    "purchase_marketplace_id": item.get("purchaseMarketplaceId"),
                    "unit_price": self._money(item.get("lineItemCost"))[0],
                    "line_item_cost": self._money(item.get("lineItemCost"))[0],
                    "shipping_cost": self._money(item.get("deliveryCost"))[0],
                    "discount_amount": self._money(item.get("discountedLineItemCost"))[0],
                    "line_item_total": self._money(item.get("total"))[0],
                    "currency": item_currency,
                    "ship_by_date": self._dt((item.get("lineItemFulfillmentInstructions") or {}).get("shipByDate")),
                    "image_url": self.repo.resolve_image_url(
                        account.id, legacy_item_id=legacy_item_id, sku=sku
                    ),
                    "variation_aspects_json": item.get("variationAspects"),
                    "raw_payload_json": item,
                }
            )

        return order_values, mapped_lines

    def _row(self, line, order, account) -> dict:
        """Build the presentation row for a single order/line item combination."""
        return {
            "id": line.id,
            "order_id": order.order_id,
            "ebay_account_id": order.ebay_account_id,
            "ebay_account_name": order.ebay_account_name or account.account_name,
            "status": order.normalized_status.value,
            "date_sold": order.creation_date,
            "date_paid": order.payment_date,
            "legacy_order_id": order.legacy_order_id,
            "sales_record_reference": order.sales_record_reference,
            "sku": line.sku,
            "item_id": line.legacy_item_id,
            "product": line.title,
            "buyer_username": order.buyer_username,
            "quantity": line.quantity,
            "item_price": line.line_item_cost,
            "shipping": line.shipping_cost,
            "total": line.line_item_total or order.order_total,
            "currency": line.currency or order.currency,
            "image_url": line.image_url,
            "seller_hub_url": f"https://www.ebay.com/sh/ord/details?orderid={order.order_id}",
        }

    def _apply_state_counts(self, state, result: AccountSyncResult) -> None:
        """Copy sync result counters into the sync state record."""
        state.pages_fetched = result.pages_fetched
        state.orders_received = result.orders_received
        state.orders_inserted = result.orders_inserted
        state.orders_updated = result.orders_updated
        state.line_items_inserted = result.line_items_inserted

    # -------------------------------------------------------------------------
    # Static helpers for data conversion
    # -------------------------------------------------------------------------

    @staticmethod
    def _dt(value: str | None) -> datetime | None:
        """Parse an ISO‑8601 datetime string (with Z) into a UTC datetime."""
        if not value:
            return None
        return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(UTC)

    @staticmethod
    def _money(node: dict | None) -> tuple[float | None, str | None]:
        """
        Extract amount and currency from an eBay money node.

        Returns (amount, currency) where amount is a float or None.
        """
        if not isinstance(node, dict):
            return None, None
        value = node.get("value")
        try:
            amount = float(value) if value not in (None, "") else None
        except (TypeError, ValueError):
            amount = None
        return amount, node.get("currency")

    @staticmethod
    def _payment_date(payments: list[dict]) -> datetime | None:
        """
        Determine the payment date by taking the latest payment that has a
        successful status (PAID, SUCCEEDED, SUCCESSFUL).
        """
        dates = [
            SoldPostingService._dt(p.get("paymentDate"))
            for p in payments
            if str(p.get("paymentStatus") or "").upper() in {"PAID", "SUCCEEDED", "SUCCESSFUL"}
            and p.get("paymentDate")
        ]
        dates = [d for d in dates if d]
        return max(dates) if dates else None

    @staticmethod
    def _ebay_datetime(value: datetime) -> str:
        """Format a datetime into the eBay API's expected string format."""
        return value.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%S.000Z")
