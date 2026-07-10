import logging
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from time import sleep
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.conversation import Conversation
from app.models.ebay_account import EbayAccount
from app.modules.integrations.ebay.oauth.token_service import EbayTokenService
from app.modules.integrations.ebay.orders.providers import FulfillmentOrderProvider, OrderPage, OrderProvider
from app.services.ebay_api_usage_service import EbayApiUsageService
from app.services.order_context_service import OrderContextService


logger = logging.getLogger(__name__)


class OrderSyncError(RuntimeError):
    pass


@dataclass(frozen=True)
class OrderSyncResult:
    account_id: UUID
    orders_processed: int
    orders_failed: int
    conversations_matched: int
    pages_processed: int
    incremental: bool
    synced_through: datetime


class EbayOrderSyncService:
    PAGE_SIZE = 200
    MAX_RETRIES = 3
    CURSOR_OVERLAP = timedelta(minutes=5)

    def __init__(self, db: Session, *, provider: OrderProvider | None = None):
        self.db = db
        self.token_service = EbayTokenService(db)
        self.provider = provider or FulfillmentOrderProvider(self.token_service.client)
        self.order_context_service = OrderContextService(db)
        self.api_usage_service = EbayApiUsageService(db)

    def sync_account(
        self,
        account_id: UUID,
        *,
        commit: bool = True,
        track_api_usage: bool = True,
    ) -> OrderSyncResult:
        account = self.db.get(EbayAccount, account_id)
        if not account:
            raise OrderSyncError('eBay account not found')
        if not account.access_token:
            raise OrderSyncError('eBay account has no access token')

        started_at = datetime.now(UTC)
        previous_cursor = account.last_order_sync_at
        filter_value = self._incremental_filter(previous_cursor, started_at)
        processed = 0
        failed = 0
        pages = 0
        offset = 0

        logger.info(
            'Starting eBay order sync account_id=%s provider=%s incremental=%s cursor=%s',
            account.id,
            type(self.provider).__name__,
            previous_cursor is not None,
            previous_cursor,
        )
        while True:
            page = self._fetch_page_with_retry(
                account,
                offset=offset,
                filter_value=filter_value,
                track_api_usage=track_api_usage,
            )
            pages += 1
            for payload in page.orders:
                try:
                    with self.db.begin_nested():
                        self.order_context_service.upsert_order_payload(account_id=account.id, payload=payload)
                        self.db.flush()
                    processed += 1
                except Exception:
                    failed += 1
                    logger.exception(
                        'Skipping invalid eBay order payload account_id=%s order_id=%s',
                        account.id,
                        payload.get('orderId'),
                    )
            self.db.flush()
            logger.warning(
                'eBay order sync page complete account_id=%s page=%s offset=%s page_orders=%s total=%s',
                account.id,
                pages,
                offset,
                len(page.orders),
                page.total,
            )
            if not page.has_more or not page.orders:
                break
            offset += len(page.orders)

        matched = self.match_account_conversations(account.id)
        account.last_order_sync_at = started_at
        if commit:
            self.db.commit()
        else:
            self.db.flush()
        logger.warning(
            'eBay order sync succeeded account_id=%s orders=%s failed=%s pages=%s conversations_matched=%s cursor=%s',
            account.id,
            processed,
            failed,
            pages,
            matched,
            started_at,
        )
        return OrderSyncResult(account.id, processed, failed, matched, pages, previous_cursor is not None, started_at)

    def match_account_conversations(self, account_id: UUID) -> int:
        conversations = self.db.scalars(
            select(Conversation)
            .where(Conversation.provider_account_id == account_id)
            .order_by(Conversation.id.asc())
        )
        matched = 0
        for conversation in conversations:
            try:
                with self.db.begin_nested():
                    mapping = self.order_context_service.link_conversation_context(
                        conversation=conversation,
                        persist_unmatched=False,
                        allow_direct_order_id=False,
                    )
                    self.db.flush()
                if mapping and mapping.order_record_id:
                    matched += 1
            except Exception:
                logger.exception(
                    'Non-fatal local order matching failure account_id=%s conversation_id=%s',
                    account_id,
                    conversation.id,
                )
        self.db.flush()
        return matched

    def _fetch_page_with_retry(
        self,
        account: EbayAccount,
        *,
        offset: int,
        filter_value: str | None,
        track_api_usage: bool,
    ) -> OrderPage:
        refreshed = False
        for attempt in range(1, self.MAX_RETRIES + 1):
            if track_api_usage:
                self.api_usage_service.reserve_calls(1)
            page = self.provider.fetch_page(
                account.access_token,
                limit=self.PAGE_SIZE,
                offset=offset,
                filter_value=filter_value,
            )
            if page.status_code == 401 and not refreshed:
                account = self.token_service.refresh_access_token(account.id)
                refreshed = True
                continue
            if page.status_code == 429 or page.status_code >= 500:
                if attempt < self.MAX_RETRIES:
                    sleep(min(2 ** (attempt - 1), 4))
                    continue
            if page.status_code < 200 or page.status_code >= 300:
                raise OrderSyncError(
                    f'eBay order listing failed with status {page.status_code}: {page.error}'
                )
            return page
        raise OrderSyncError('eBay order listing failed after retries')

    def _incremental_filter(self, cursor: datetime | None, end: datetime) -> str | None:
        if cursor is None:
            return None
        start = cursor - self.CURSOR_OVERLAP
        return f'lastmodifieddate:[{self._ebay_datetime(start)}..{self._ebay_datetime(end)}]'

    @staticmethod
    def _ebay_datetime(value: datetime) -> str:
        normalized = value.astimezone(UTC)
        return normalized.strftime('%Y-%m-%dT%H:%M:%S.000Z')
