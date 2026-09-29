import logging
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from time import perf_counter
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.conversation import SyncLog, SyncLogStatus
from app.models.app_config import AppConfigSetting
from app.models.ebay_account import EbayAccount, EbayConnectionStatus
from app.modules.integrations.ebay.oauth.token_service import EbayTokenService
from app.modules.integrations.ebay.providers import EBAY_PROVIDER_NAME
from app.modules.integrations.ebay.services.ebay_message_service import EbayMessageService
from app.modules.integrations.ebay.services.ebay_best_offer_sync_service import EbayBestOfferSyncService
from app.modules.integrations.ebay.services.ebay_conversation_offer_resolver import EbayConversationOfferResolver
from app.modules.integrations.ebay.services.ebay_order_sync_service import EbayOrderSyncService
from app.services.ebay_api_usage_service import EbayApiUsageService
from app.services.conversation_product_context_service import ConversationProductContextService
from app.services.order_context_service import OrderContextService
from app.services.sync_log_service import SyncLogService

logger = logging.getLogger(__name__)

EBAY_MESSAGE_SYNC_TYPE = 'EBAY_MESSAGE_SYNC'
EBAY_CONVERSATION_TYPES = ('FROM_MEMBERS', 'FROM_EBAY')
SYNC_OVERLAP = timedelta(minutes=1)
DEFAULT_NOTIFICATION_SYNC_INTERVAL_MINUTES = 60


@dataclass(frozen=True)
class EbaySyncResult:
    account_id: UUID
    ebay_username: str
    sync_log_id: UUID
    status: str
    conversations_processed: int
    conversations_failed: int
    conversations_created: int
    conversations_updated: int
    messages_created: int
    messages_updated: int
    failed_conversation_ids: list[str]
    total_conversations_available: int | None = None
    elapsed_seconds: float | None = None
    average_detail_seconds: float | None = None
    error_message: str | None = None


class EbaySyncService:
    def __init__(self, db: Session):
        self.db = db
        self.token_service = EbayTokenService(db)
        self.message_service = EbayMessageService(db)
        self.sync_log_service = SyncLogService(db)
        self.api_usage_service = EbayApiUsageService(db)
        self.order_context_service = OrderContextService(db)
        self.order_sync_service = EbayOrderSyncService(db)
        self.product_context_service = ConversationProductContextService(db)
        self.best_offer_sync_service = EbayBestOfferSyncService(db)
        self.conversation_offer_resolver = EbayConversationOfferResolver(db)
        logger.warning("EbaySyncService initialized")

    # ebay_sync_service.py - Refactored version

    def sync_account(
        self,
        account_id: UUID,
        *,
        max_conversations: int | None = None,
        sync_log_id: UUID | None = None,
    ) -> EbaySyncResult:
        account = self._get_syncable_account(account_id)
        updated_since = self._sync_window_start(account.last_sync_at)

        # Worker jobs reuse the RUNNING log created by the API before the
        # child process starts. Direct callers still create their own log.
        sync_log = self._start_sync_log(
            account,
            max_conversations,
            updated_since,
            sync_log_id=sync_log_id,
        )
        counters = self._initialize_counters()
        sync_context = self._initialize_sync_context(account, updated_since, max_conversations)

        try:
            account = self._ensure_access_token(account)
            sync_context['notification_sync_plan'] = self._notification_sync_plan(account, sync_context['sync_started_at_utc'])
            
            # Process conversations
            self._process_conversations(account, updated_since, max_conversations, sync_log, counters, sync_context)
            
            # Sync related data
            order_sync_result, order_sync_error = self._sync_related_data(account, sync_context)

            # Complete sync
            return self._finalize_sync(account, 
                                        sync_log, 
                                        counters, 
                                        sync_context, 
                                        order_sync_result, 
                                        order_sync_error
                                    )
            
        except Exception as exc:
            return self._handle_sync_failure(account_id, account, sync_log, counters, sync_context, exc)


    def _start_sync_log(
        self,
        account: EbayAccount,
        max_conversations: int | None,
        updated_since: datetime | None,
        *,
        sync_log_id: UUID | None = None,
    ) -> SyncLog:
        """Create a sync log or reuse the log reserved by the worker coordinator."""
        if sync_log_id is not None:
            sync_log = self.db.get(SyncLog, sync_log_id)
            if not sync_log:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='Sync log not found')
            if sync_log.provider_account_id != account.id:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail='Sync log does not belong to the requested eBay account',
                )
            if sync_log.status != SyncLogStatus.RUNNING:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail=f'Sync log is not running: {sync_log.status.value}',
                )
            return sync_log

        return self.sync_log_service.start_sync(
            provider=EBAY_PROVIDER_NAME,
            provider_account_id=account.id,
            sync_type=EBAY_MESSAGE_SYNC_TYPE,
            sync_metadata={
                'provider': EBAY_PROVIDER_NAME.upper(),
                'conversation_types': list(EBAY_CONVERSATION_TYPES),
                'max_conversations': max_conversations,
                'updated_since': updated_since.isoformat() if updated_since else None,
                'incremental': updated_since is not None,
                'execution_mode': 'DIRECT',
            },
        )


    def queue_sync_account(
        self,
        account_id: UUID,
        *,
        max_conversations: int | None = None,
        trigger: str = 'MANUAL',
    ) -> SyncLog:
        """
        Reserve a sync job before starting a separate OS process.

        The account row is locked while checking for another RUNNING sync,
        preventing double-clicks and overlapping scheduler ticks.
        """
        account = self.db.scalar(
            select(EbayAccount)
            .where(EbayAccount.id == account_id)
            .with_for_update()
        )
        if not account:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='eBay account not found')
        if not account.is_active:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail='eBay account is inactive')
        if account.connection_status != EbayConnectionStatus.CONNECTED:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f'eBay account is not connected. Current status: {account.connection_status.value}',
            )

        running_log = self.db.scalar(
            select(SyncLog)
            .where(
                SyncLog.provider == EBAY_PROVIDER_NAME,
                SyncLog.provider_account_id == account.id,
                SyncLog.sync_type == EBAY_MESSAGE_SYNC_TYPE,
                SyncLog.status == SyncLogStatus.RUNNING,
            )
            .order_by(SyncLog.started_at.desc())
        )
        if running_log:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail='An eBay sync is already running for this account',
            )

        updated_since = self._sync_window_start(account.last_sync_at)
        sync_log = self.sync_log_service.start_sync(
            provider=EBAY_PROVIDER_NAME,
            provider_account_id=account.id,
            sync_type=EBAY_MESSAGE_SYNC_TYPE,
            sync_metadata={
                'provider': EBAY_PROVIDER_NAME.upper(),
                'conversation_types': list(EBAY_CONVERSATION_TYPES),
                'max_conversations': max_conversations,
                'updated_since': updated_since.isoformat() if updated_since else None,
                'incremental': updated_since is not None,
                'execution_mode': 'PROCESS',
                'trigger': trigger,
            },
        )
        account.sync_status = 'SYNCING'
        self.db.commit()
        self.db.refresh(sync_log)
        return sync_log


    def queue_sync_all_connected_accounts(
        self,
        *,
        max_conversations: int | None = None,
        trigger: str = 'MANUAL_ALL',
    ) -> list[tuple[EbayAccount, SyncLog]]:
        """Queue every connected active account; no eBay API work occurs here."""
        accounts = list(
            self.db.scalars(
                select(EbayAccount)
                .where(EbayAccount.connection_status == EbayConnectionStatus.CONNECTED)
                .where(EbayAccount.is_active.is_(True))
                .order_by(EbayAccount.created_at.asc())
            )
        )
        queued: list[tuple[EbayAccount, SyncLog]] = []
        for account in accounts:
            try:
                sync_log = self.queue_sync_account(
                    account.id,
                    max_conversations=max_conversations,
                    trigger=trigger,
                )
            except HTTPException as exc:
                if exc.status_code == status.HTTP_409_CONFLICT:
                    self.db.rollback()
                    existing = self.db.scalar(
                        select(SyncLog)
                        .where(
                            SyncLog.provider == EBAY_PROVIDER_NAME,
                            SyncLog.provider_account_id == account.id,
                            SyncLog.sync_type == EBAY_MESSAGE_SYNC_TYPE,
                            SyncLog.status == SyncLogStatus.RUNNING,
                        )
                        .order_by(SyncLog.started_at.desc())
                    )
                    if existing:
                        queued.append((account, existing))
                        continue
                raise
            queued.append((account, sync_log))
        return queued


    def _initialize_counters(self) -> dict:
        """Initialize counters dictionary."""
        return {
            'conversations_processed': 0,
            'conversations_failed': 0,
            'conversations_created': 0,
            'conversations_updated': 0,
            'messages_created': 0,
            'messages_updated': 0,
        }


    def _initialize_sync_context(self, account: EbayAccount, updated_since: datetime | None, max_conversations: int | None) -> dict:
        """Initialize sync context."""
        return {
            'account': account,
            'updated_since': updated_since,
            'max_conversations': max_conversations,
            'total_conversations_available': None,
            'detail_seconds_total': 0.0,
            'sync_started_at': perf_counter(),
            'sync_started_at_utc': datetime.now(UTC),
            'failed_conversations': [],
            'enrichment_failed_conversation_ids': [],
            'touched_listing_ids': set(),
            'notification_sync_plan': {'due': False, 'updated_since': updated_since},
        }


    def _process_conversations(
        self,
        account: EbayAccount,
        updated_since: datetime | None,
        max_conversations: int | None,
        sync_log: SyncLog,
        counters: dict,
        sync_context: dict,
    ) -> None:
        """Process all conversations from eBay."""
        for conversation_summary, page_total in self._iter_conversation_summaries(
            account,
            max_conversations=max_conversations,
            updated_since=updated_since,
            notification_plan=sync_context['notification_sync_plan'],
        ):
            if page_total is not None:
                sync_context['total_conversations_available'] = page_total
                
            conversation_id = self._conversation_id(conversation_summary)
            if not conversation_id:
                logger.warning('Skipping eBay conversation without conversationId for account %s', account.id)
                continue

            self._process_single_conversation(
                account,
                conversation_summary,
                conversation_id,
                sync_log,
                counters,
                sync_context
            )


    def _process_single_conversation(
        self,
        account: EbayAccount,
        conversation_summary: dict,
        conversation_id: str,
        sync_log: SyncLog,
        counters: dict,
        sync_context: dict,
    ) -> None:
        """Process a single conversation."""
        conversation_type = self._conversation_type(conversation_summary)
        detail_started_at = perf_counter()
        
        detail_response = self._get_conversation_detail_with_retry(
            account,
            conversation_id=conversation_id,
            conversation_type=conversation_type,
            limit=50,
            offset=0,
        )

        self._log_conversation_detail_diagnostic(account, conversation_id, conversation_type, conversation_summary, detail_response)

        if not detail_response.ok or not isinstance(detail_response.payload, dict):
            self._handle_failed_conversation_detail(account, conversation_id, conversation_type, conversation_summary, detail_response, counters, sync_context)
            return

        try:
            # Fetch every message page before marking this conversation imported.
            conversation_detail = self._complete_conversation_detail(
                account, conversation_id, conversation_type, detail_response.payload
            )
            self._process_conversation_detail(
                account,
                conversation_summary,
                conversation_id,
                conversation_type,
                conversation_detail,
                detail_started_at,
                counters,
                sync_context
            )
            self._log_sync_progress(account, conversation_id, counters, sync_context)
            self._update_sync_progress(sync_log, counters, sync_context)
            
        except Exception as conversation_exc:
            self._handle_conversation_processing_error(account, conversation_id, conversation_type, conversation_exc, counters, sync_context)


    def _process_conversation_detail(
        self,
        account: EbayAccount,
        conversation_summary: dict,
        conversation_id: str,
        conversation_type: str,
        conversation_detail: dict,
        detail_started_at: float,
        counters: dict,
        sync_context: dict,
    ) -> None:
        """Process the conversation detail data."""
        with self.db.begin_nested():
            detail_elapsed_seconds = perf_counter() - detail_started_at
            sync_context['detail_seconds_total'] += detail_elapsed_seconds
            
            conversation, created = self.message_service.upsert_conversation(
                account=account,
                conversation_summary=conversation_summary,
                conversation_detail=conversation_detail,
                conversation_type=conversation_type,
            )

            if conversation.reference_id and conversation.provider_conversation_type == 'FROM_MEMBERS':
                sync_context['touched_listing_ids'].add(conversation.reference_id)

            self.db.flush()

            messages_created, messages_updated = self.message_service.upsert_messages(
                account=account,
                conversation=conversation,
                conversation_detail=conversation_detail,
            )
            self.db.flush()
            # Enrichment failures must not erase the conversation or messages.
            enrichment_failed = False
            for enrich in (
                self.product_context_service.enrich_conversation,
                self.conversation_offer_resolver.resolve_for_conversation,
            ):
                try:
                    with self.db.begin_nested():
                        enrich(conversation)
                        self.db.flush()
                except Exception:
                    enrichment_failed = True
                    logger.exception('eBay conversation enrichment failed account_id=%s conversation_id=%s', account.id, conversation_id)
            enrichment_failed = enrichment_failed or bool(conversation.raw_payload.get('offer_resolution_failed'))

        # Only count imports after their savepoint has successfully flushed.
        counters['conversations_processed'] += 1
        counters['conversations_created' if created else 'conversations_updated'] += 1
        counters['messages_created'] += messages_created
        counters['messages_updated'] += messages_updated
        if enrichment_failed:
            sync_context['enrichment_failed_conversation_ids'].append(conversation_id)

    def _complete_conversation_detail(
        self,
        account: EbayAccount,
        conversation_id: str,
        conversation_type: str,
        first_page: dict,
    ) -> dict:
        detail = dict(first_page)
        if not isinstance(first_page.get('messages'), list):
            raise ValueError('eBay conversation detail omitted messages')
        messages = list(first_page['messages'])
        page = first_page
        offset = 0
        while True:
            total = page.get('total')
            next_offset = offset + 50
            if not page.get('next') and (not isinstance(total, int) or next_offset >= total):
                break
            response = self._get_conversation_detail_with_retry(
                account, conversation_id=conversation_id,
                conversation_type=conversation_type, limit=50, offset=next_offset,
            )
            if not response.ok or not isinstance(response.payload, dict):
                raise RuntimeError(f'eBay conversation detail page failed at offset {next_offset}: HTTP {response.status_code}')
            page = response.payload
            page_messages = page.get('messages')
            if not isinstance(page_messages, list) or not page_messages:
                raise ValueError(f'eBay conversation detail page unexpectedly empty at offset {next_offset}')
            messages.extend(page_messages)
            offset = next_offset
        detail['messages'] = messages
        total = first_page.get('total')
        if isinstance(total, int) and len(messages) < total:
            raise ValueError('eBay conversation detail returned fewer messages than total')
        for message in messages:
            message_id = message.get('messageId') if isinstance(message, dict) else None
            if not isinstance(message_id, str) or not message_id.strip():
                raise ValueError('eBay conversation detail contains a message without messageId')
        detail.pop('next', None)
        return detail


    def _handle_failed_conversation_detail(
        self,
        account: EbayAccount,
        conversation_id: str,
        conversation_type: str,
        conversation_summary: dict,
        detail_response,
        counters: dict,
        sync_context: dict,
    ) -> None:
        """Handle failed conversation detail request."""
        failed_conversation = self._failed_conversation(
            conversation_id=conversation_id,
            conversation_type=conversation_type,
            status_code=detail_response.status_code,
            error_message='eBay conversation detail request failed',
        )
        failed_conversation['response_body'] = detail_response.payload
        failed_conversation['diagnostic'] = self._conversation_detail_diagnostic(
            conversation_summary=conversation_summary,
            detail_response=detail_response,
        )
        sync_context['failed_conversations'].append(failed_conversation)
        counters['conversations_failed'] += 1
        
        logger.warning(
            'Skipping failed eBay conversation detail account_id=%s conversation_id=%s conversation_type=%s status_code=%s',
            account.id,
            conversation_id,
            conversation_type,
            detail_response.status_code,
        )


    def _handle_conversation_processing_error(
        self,
        account: EbayAccount,
        conversation_id: str,
        conversation_type: str,
        error: Exception,
        counters: dict,
        sync_context: dict,
    ) -> None:
        """Handle conversation processing error."""
        sync_context['failed_conversations'].append(
            self._failed_conversation(
                conversation_id=conversation_id,
                conversation_type=conversation_type,
                status_code=None,
                error_message=str(error),
            )
        )
        counters['conversations_failed'] += 1
        logger.exception(
            'Skipping eBay conversation after processing failure account_id=%s conversation_id=%s conversation_type=%s',
            account.id,
            conversation_id,
            conversation_type,
        )


    def _log_conversation_detail_diagnostic(
        self,
        account: EbayAccount,
        conversation_id: str,
        conversation_type: str,
        conversation_summary: dict,
        detail_response,
    ) -> None:
        """Log conversation detail diagnostic information."""
        logger.info(
            'eBay conversation detail diagnostic account_id=%s conversation_id=%s conversation_type=%s request_url=%s request_headers=%s',
            account.id,
            conversation_id,
            conversation_type,
            detail_response.request_url,
            detail_response.request_headers,
        )
        if not detail_response.ok:
            logger.warning(
                'eBay conversation detail response diagnostic account_id=%s status_code=%s response_body=%s diagnostic=%s',
                account.id,
                detail_response.status_code,
                detail_response.payload,
                self._conversation_detail_diagnostic(
                    conversation_summary=conversation_summary,
                    detail_response=detail_response,
                ),
            )


    def _log_sync_progress(
        self,
        account: EbayAccount,
        conversation_id: str,
        counters: dict,
        sync_context: dict,
    ) -> None:
        """Log sync progress."""
        elapsed_seconds = perf_counter() - sync_context['sync_started_at']
        remaining_count = self._remaining_count(
            total_conversations_available=sync_context['total_conversations_available'],
            max_conversations=sync_context['max_conversations'],
            conversations_processed=counters['conversations_processed'] + counters['conversations_failed'],
        )
        logger.warning(
            'eBay sync progress account_id=%s processed=%s current_conversation_id=%s elapsed_seconds=%.2f remaining_count=%s',
            account.id,
            counters['conversations_processed'],
            conversation_id,
            elapsed_seconds,
            remaining_count,
        )


    def _update_sync_progress(
        self,
        sync_log: SyncLog,
        counters: dict,
        sync_context: dict,
    ) -> None:
        """Update sync progress in the database."""
        if counters['conversations_processed'] % 25 == 0:
            self.sync_log_service.update_progress(
                sync_log.id,
                records_processed=self._records_processed(counters),
                sync_metadata=self._progress_metadata(
                    counters=counters,
                    total_conversations_available=sync_context['total_conversations_available'],
                    max_conversations=sync_context['max_conversations'],
                    updated_since=sync_context['updated_since'],
                    elapsed_seconds=perf_counter() - sync_context['sync_started_at'],
                    detail_seconds_total=sync_context['detail_seconds_total'],
                    failed_conversations=sync_context['failed_conversations'],
                ),
            )


    def _sync_related_data(self, account: EbayAccount, sync_context: dict) -> tuple[any, str | None]:
        """Sync related data (orders, offers)."""
        order_sync_result = None
        order_sync_error = None

        # Sync orders
        try:
            order_sync_result = self.order_sync_service.sync_account(
                account.id,
                commit=False,
                track_api_usage=True,
            )
        except Exception as exc:
            order_sync_error = str(exc)
            logger.exception('Non-fatal eBay order sync failure account_id=%s', account.id)

        # Sync best offers only for touched listings
        touched_listing_ids = list(sync_context.get('touched_listing_ids', []))
        if touched_listing_ids:
            self.best_offer_sync_service.sync_account(account.id, listing_ids=touched_listing_ids, commit=False)
        else:
            # Skip entirely to save API calls – no listings were updated in this sync
            logger.info('No touched listings, skipping BestOffer sync for account_id=%s', account.id)

        return order_sync_result, order_sync_error


    def _finalize_sync(
        self,
        account: EbayAccount,
        sync_log: SyncLog,
        counters: dict,
        sync_context: dict,
        order_sync_result: any,
        order_sync_error: str | None,
    ) -> EbaySyncResult:
        """Finalize the sync process."""
        enrichment_failures = sync_context['enrichment_failed_conversation_ids']
        if not counters['conversations_failed'] and not enrichment_failures and not sync_context['max_conversations']:
            account.last_sync_at = sync_context['sync_started_at_utc']
        account.sync_status = (
            'SUCCESS_WITH_ERRORS'
            if counters['conversations_failed'] or enrichment_failures or order_sync_error or (order_sync_result and order_sync_result.orders_failed)
            else 'SUCCESS'
        )
        
        elapsed_seconds = perf_counter() - sync_context['sync_started_at']
        
        sync_log = self.sync_log_service.complete_sync(
            sync_log.id,
            records_processed=self._records_processed(counters),
        )
        
        self._set_sync_error_messages(sync_log, counters, order_sync_result, order_sync_error)
        if enrichment_failures:
            sync_log.error_message = '; '.join(filter(None, [
                sync_log.error_message,
                f'{len(enrichment_failures)} conversation(s) failed during enrichment',
            ]))
        self._set_sync_metadata(sync_log, counters, sync_context, elapsed_seconds, order_sync_result, order_sync_error)
        
        self.db.commit()
        
        logger.warning(
            'eBay message sync succeeded account_id=%s conversations=%s messages_created=%s messages_updated=%s elapsed_seconds=%.2f',
            account.id,
            counters['conversations_processed'],
            counters['messages_created'],
            counters['messages_updated'],
            elapsed_seconds,
        )
        
        return self._build_result(
            account=account,
            sync_log_id=sync_log.id,
            status=account.sync_status,
            counters=counters,
            failed_conversations=sync_context['failed_conversations'],
            total_conversations_available=sync_context['total_conversations_available'],
            elapsed_seconds=elapsed_seconds,
            average_detail_seconds=self._average_detail_seconds(
                sync_context['detail_seconds_total'],
                counters['conversations_processed'],
            ),
        )


    def _set_sync_error_messages(
        self,
        sync_log: SyncLog,
        counters: dict,
        order_sync_result: any,
        order_sync_error: str | None,
    ) -> None:
        """Set error messages on the sync log."""
        if counters['conversations_failed'] or order_sync_error or (order_sync_result and order_sync_result.orders_failed):
            errors = []
            if counters['conversations_failed']:
                errors.append(f"{counters['conversations_failed']} conversation(s) failed during sync")
            if order_sync_error:
                errors.append(f'Order sync failed: {order_sync_error}')
            if order_sync_result and order_sync_result.orders_failed:
                errors.append(f'{order_sync_result.orders_failed} order payload(s) failed during sync')
            sync_log.error_message = '; '.join(errors)


    def _set_sync_metadata(
        self,
        sync_log: SyncLog,
        counters: dict,
        sync_context: dict,
        elapsed_seconds: float,
        order_sync_result: any,
        order_sync_error: str | None,
    ) -> None:
        """Set metadata on the sync log."""
        sync_log.sync_metadata = {
            **(sync_log.sync_metadata or {}),
            **self._progress_metadata(
                counters=counters,
                total_conversations_available=sync_context['total_conversations_available'],
                max_conversations=sync_context['max_conversations'],
                updated_since=sync_context['updated_since'],
                elapsed_seconds=elapsed_seconds,
                detail_seconds_total=sync_context['detail_seconds_total'],
                failed_conversations=sync_context['failed_conversations'],
            ),
            'order_sync': {
                'orders_processed': order_sync_result.orders_processed if order_sync_result else 0,
                'orders_failed': order_sync_result.orders_failed if order_sync_result else 0,
                'pages_processed': order_sync_result.pages_processed if order_sync_result else 0,
                'conversations_matched': order_sync_result.conversations_matched if order_sync_result else 0,
                'incremental': order_sync_result.incremental if order_sync_result else None,
                'error': order_sync_error,
            },
            'enrichment_failed_conversation_ids': sync_context['enrichment_failed_conversation_ids'],
            'notification_sync': self._notification_sync_metadata(counters, sync_context),
        }


    def _handle_sync_failure(
        self,
        account_id: UUID,
        account: EbayAccount | None,
        sync_log: SyncLog,
        counters: dict,
        sync_context: dict,
        exc: Exception,
    ) -> EbaySyncResult:
        """Handle sync failure."""
        self.db.rollback()
        failed_sync_log = self.sync_log_service.fail_sync(sync_log.id, str(exc))
        
        account = self.db.get(EbayAccount, account_id)
        if account:
            account.sync_status = 'FAILED'
            self.db.commit()
        
        logger.exception('eBay message sync failed for account %s', account_id)
        
        return self._build_result(
            account=account or self._get_syncable_account(account_id),
            sync_log_id=failed_sync_log.id,
            status=failed_sync_log.status.value,
            counters=counters,
            failed_conversations=sync_context.get('failed_conversations', []),
            total_conversations_available=sync_context.get('total_conversations_available'),
            elapsed_seconds=perf_counter() - sync_context.get('sync_started_at', 0),
            average_detail_seconds=self._average_detail_seconds(
                sync_context.get('detail_seconds_total', 0.0),
                counters['conversations_processed'],
            ),
            error_message=str(exc),
        )


    def sync_all_connected_accounts(self) -> list[EbaySyncResult]:
        statement = (
            select(EbayAccount)
            .where(EbayAccount.connection_status == EbayConnectionStatus.CONNECTED)
            .where(EbayAccount.is_active.is_(True))
            .order_by(EbayAccount.created_at.asc())
        )
        accounts = list(self.db.scalars(statement))
        return [self.sync_account(account.id) for account in accounts]

    def _iter_conversation_summaries(
        self,
        account: EbayAccount,
        *,
        max_conversations: int | None = None,
        updated_since: datetime | None = None,
        notification_plan: dict | None = None,
    ):
        limit = 50
        yielded_count = 0
        # Routine syncs retain the former old-page stopping behavior. A due
        # extended scan reconciles later pages using the older saved cutoff,
        # since eBay does not guarantee ordering by latest-message activity.
        extended_scan = notification_plan is None or notification_plan['due'] or updated_since is None
        for conversation_type in EBAY_CONVERSATION_TYPES:
            if conversation_type == 'FROM_EBAY' and notification_plan is not None and not notification_plan['due']:
                continue
            cutoff = notification_plan['updated_since'] if notification_plan is not None and notification_plan['due'] else updated_since
            offset = 0
            while True:
                response = self._get_conversations_with_retry(
                    account,
                    conversation_type=conversation_type,
                    limit=limit,
                    offset=offset,
                    # Provider time filtering can omit replies in older member
                    # threads. Compare latest-message activity locally instead.
                    start_time=None,
                )
                if not response.ok or not isinstance(response.payload, dict):
                    logger.warning(
                        'eBay conversation list request failed account_id=%s conversation_type=%s offset=%s status_code=%s response_body=%s',
                        account.id,
                        conversation_type,
                        offset,
                        response.status_code,
                        response.payload,
                    )
                    raise HTTPException(
                        status_code=status.HTTP_502_BAD_GATEWAY,
                        detail='eBay conversation list request failed',
                    )

                payload = response.payload
                total = payload.get('total')
                page_total = total if isinstance(total, int) else None
                conversations = payload.get('conversations') if isinstance(payload.get('conversations'), list) else []
                logger.warning(
                    'eBay conversation list page fetched account_id=%s type=%s offset=%s limit=%s page_count=%s total_available=%s max_conversations=%s updated_since=%s status_code=%s',
                    account.id,
                    conversation_type,
                    offset,
                    limit,
                    len(conversations),
                    page_total,
                    max_conversations,
                    cutoff.isoformat() if cutoff else None,
                    response.status_code,
                )
                if conversation_type == 'FROM_MEMBERS' and offset == 0 and cutoff and not conversations:
                    logger.warning(
                        'eBay returned no member conversations for window account_id=%s updated_since=%s; '
                        'verify the account and provider response if messages are visible on eBay',
                        account.id, cutoff.isoformat(),
                    )
                old_count = 0
                for conversation in conversations:
                    if isinstance(conversation, dict):
                        conversation.setdefault('conversationType', conversation_type)
                        last_activity_at = self._conversation_activity_at(conversation)
                        if conversation_type == 'FROM_EBAY' and last_activity_at is None:
                            last_activity_at = self._parse_ebay_datetime(conversation.get('createdDate'))

                        if cutoff and last_activity_at and last_activity_at < cutoff:
                            old_count += 1
                            continue

                        yield conversation, page_total
                        yielded_count += 1
                        if max_conversations and yielded_count >= max_conversations:
                            return

                if not conversations:
                    break
                if not extended_scan and cutoff and old_count == len(conversations):
                    logger.warning('Stopping routine eBay summary scan at old page account_id=%s type=%s offset=%s cutoff=%s; later pages reconcile on the extended scan',
                                   account.id, conversation_type, offset, cutoff.isoformat())
                    break
                offset += limit
                if page_total is not None and offset >= page_total:
                    break

    def _notification_sync_plan(self, account: EbayAccount, now: datetime) -> dict:
        configured_interval = self.db.scalar(select(AppConfigSetting.value).where(
            AppConfigSetting.config_key == 'api.ebay_notification_sync_interval_minutes'))
        interval = max(1, int(configured_interval)) if configured_interval is not None else DEFAULT_NOTIFICATION_SYNC_INTERVAL_MINUTES
        previous = self.db.scalar(select(SyncLog).where(
            SyncLog.provider == EBAY_PROVIDER_NAME,
            SyncLog.provider_account_id == account.id,
            SyncLog.sync_type == EBAY_MESSAGE_SYNC_TYPE,
            SyncLog.status == SyncLogStatus.SUCCESS,
            SyncLog.sync_metadata['notification_sync']['completed'].as_boolean() == True,
        ).order_by(SyncLog.started_at.desc()).limit(1))
        previous_at = (self._parse_ebay_datetime(previous.sync_metadata['notification_sync'].get('synced_through'))
                       if previous is not None else None)
        due = previous_at is None or now >= previous_at + timedelta(minutes=interval)
        cutoff = self._sync_window_start(previous_at if previous_at is not None else account.last_sync_at)
        logger.warning('eBay notification sync plan account_id=%s due=%s interval_minutes=%s updated_since=%s',
                       account.id, due, interval, cutoff.isoformat() if cutoff else None)
        return {'due': due, 'updated_since': cutoff, 'interval_minutes': interval}

    def _notification_sync_metadata(self, counters: dict, sync_context: dict) -> dict:
        plan = sync_context['notification_sync_plan']
        completed = (plan['due'] and not counters['conversations_failed']
                     and not sync_context['enrichment_failed_conversation_ids'] and not sync_context['max_conversations'])
        cutoff = plan['updated_since']
        return {
            'included': plan['due'], 'completed': bool(completed),
            'member_reconciliation_included': plan['due'],
            'interval_minutes': plan.get('interval_minutes', DEFAULT_NOTIFICATION_SYNC_INTERVAL_MINUTES),
            'updated_since': cutoff.isoformat() if cutoff else None,
            'synced_through': sync_context['sync_started_at_utc'].isoformat() if completed else None,
        }

    def _get_syncable_account(self, account_id: UUID) -> EbayAccount:
        account = self.db.get(EbayAccount, account_id)
        if not account:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='eBay account not found')
        if not account.is_active:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail='eBay account is inactive')
        if account.connection_status != EbayConnectionStatus.CONNECTED:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f'eBay account is not connected. Current status: {account.connection_status.value}',
            )
        return account

    def _ensure_access_token(self, account: EbayAccount) -> EbayAccount:
        if not account.access_token or (
            account.access_token_expires_at and account.access_token_expires_at <= datetime.now(UTC)
        ):
            return self.token_service.refresh_access_token(account.id)
        return account

    def _refresh_account_after_unauthorized(self, account: EbayAccount) -> EbayAccount:
        logger.warning('Refreshing eBay access token after 401 account_id=%s', account.id)
        refreshed_account = self.token_service.refresh_access_token(account.id)
        self.db.refresh(refreshed_account)
        return refreshed_account

    def _get_conversations_with_retry(
        self,
        account: EbayAccount,
        *,
        conversation_type: str,
        limit: int,
        offset: int,
        start_time: datetime | None = None,
    ):
        self.api_usage_service.reserve_calls(1, EbayApiUsageService.COMMERCE)
        response = self.token_service.client.get_conversations_raw(
            account.access_token,
            conversation_type=conversation_type,
            limit=limit,
            offset=offset,
            start_time=start_time,
        )
        if response.status_code != status.HTTP_401_UNAUTHORIZED:
            return response

        account = self._refresh_account_after_unauthorized(account)
        self.api_usage_service.reserve_calls(1, EbayApiUsageService.COMMERCE)
        return self.token_service.client.get_conversations_raw(
            account.access_token,
            conversation_type=conversation_type,
            limit=limit,
            offset=offset,
            start_time=start_time,
        )

    def _get_conversation_detail_with_retry(
        self,
        account: EbayAccount,
        *,
        conversation_id: str,
        conversation_type: str,
        limit: int,
        offset: int,
    ):
        self.api_usage_service.reserve_calls(1, EbayApiUsageService.COMMERCE)
        response = self.token_service.client.get_conversation_raw(
            account.access_token,
            conversation_id=conversation_id,
            conversation_type=conversation_type,
            limit=limit,
            offset=offset,
        )
        if response.status_code != status.HTTP_401_UNAUTHORIZED:
            return response

        account = self._refresh_account_after_unauthorized(account)
        self.api_usage_service.reserve_calls(1, EbayApiUsageService.COMMERCE)
        return self.token_service.client.get_conversation_raw(
            account.access_token,
            conversation_id=conversation_id,
            conversation_type=conversation_type,
            limit=limit,
            offset=offset,
        )

    def _conversation_id(self, conversation_summary: dict) -> str | None:
        conversation_id = conversation_summary.get('conversationId')
        if isinstance(conversation_id, str) and conversation_id.strip():
            return conversation_id.strip()
        return None

    def _conversation_type(self, conversation_summary: dict) -> str:
        conversation_type = conversation_summary.get('conversationType')
        if isinstance(conversation_type, str) and conversation_type.strip():
            return conversation_type.strip()
        return 'FROM_MEMBERS'

    def _sync_window_start(self, last_sync_at: datetime | None) -> datetime | None:
        if last_sync_at is None:
            return None
        normalized = last_sync_at.astimezone(UTC) if last_sync_at.tzinfo else last_sync_at.replace(tzinfo=UTC)
        return normalized - SYNC_OVERLAP

    def _conversation_activity_at(self, conversation_summary: dict) -> datetime | None:
        latest_message = conversation_summary.get('latestMessage')
        if isinstance(latest_message, dict):
            parsed_latest_message = self._parse_ebay_datetime(latest_message.get('createdDate'))
            if parsed_latest_message:
                return parsed_latest_message
        # Creation time cannot establish whether an existing thread changed.
        return None

    def _parse_ebay_datetime(self, value: object) -> datetime | None:
        if not isinstance(value, str) or not value.strip():
            return None
        normalized_value = value.strip()
        if normalized_value.endswith('Z'):
            normalized_value = f'{normalized_value[:-1]}+00:00'
        try:
            parsed_value = datetime.fromisoformat(normalized_value)
        except ValueError:
            return None
        if parsed_value.tzinfo is None:
            return parsed_value.replace(tzinfo=UTC)
        return parsed_value

    def _build_result(
        self,
        *,
        account: EbayAccount,
        sync_log_id: UUID,
        status: SyncLogStatus | str,
        counters: dict,
        failed_conversations: list[dict],
        total_conversations_available: int | None = None,
        elapsed_seconds: float | None = None,
        average_detail_seconds: float | None = None,
        error_message: str | None = None,
    ) -> EbaySyncResult:
        return EbaySyncResult(
            account_id=account.id,
            ebay_username=account.ebay_username,
            sync_log_id=sync_log_id,
            status=status.value if isinstance(status, SyncLogStatus) else status,
            conversations_processed=counters['conversations_processed'],
            conversations_failed=counters['conversations_failed'],
            conversations_created=counters['conversations_created'],
            conversations_updated=counters['conversations_updated'],
            messages_created=counters['messages_created'],
            messages_updated=counters['messages_updated'],
            failed_conversation_ids=[
                failed_conversation['conversation_id']
                for failed_conversation in failed_conversations
                if failed_conversation.get('conversation_id')
            ],
            total_conversations_available=total_conversations_available,
            elapsed_seconds=elapsed_seconds,
            average_detail_seconds=average_detail_seconds,
            error_message=error_message,
        )

    def _records_processed(self, counters: dict) -> int:
        return counters['conversations_processed'] + counters['messages_created'] + counters['messages_updated']

    def _remaining_count(
        self,
        *,
        total_conversations_available: int | None,
        max_conversations: int | None,
        conversations_processed: int,
    ) -> int | None:
        if total_conversations_available is None:
            return None
        target_count = min(total_conversations_available, max_conversations) if max_conversations else total_conversations_available
        return max(target_count - conversations_processed, 0)

    def _average_detail_seconds(self, detail_seconds_total: float, conversations_processed: int) -> float | None:
        if conversations_processed <= 0:
            return None
        return detail_seconds_total / conversations_processed

    def _progress_metadata(
        self,
        *,
        counters: dict,
        total_conversations_available: int | None,
        max_conversations: int | None,
        updated_since: datetime | None,
        elapsed_seconds: float,
        detail_seconds_total: float,
        failed_conversations: list[dict],
    ) -> dict:
        average_detail_seconds = self._average_detail_seconds(
            detail_seconds_total,
            counters['conversations_processed'],
        )
        return {
            'provider': EBAY_PROVIDER_NAME.upper(),
            'conversation_types': list(EBAY_CONVERSATION_TYPES),
            'max_conversations': max_conversations,
            'updated_since': updated_since.isoformat() if updated_since else None,
            'incremental': updated_since is not None,
            'total_conversations_available': total_conversations_available,
            'conversations_processed': counters['conversations_processed'],
            'conversations_failed': counters['conversations_failed'],
            'failed_conversation_ids': [
                failed_conversation['conversation_id']
                for failed_conversation in failed_conversations
                if failed_conversation.get('conversation_id')
            ],
            'failed_conversations': failed_conversations,
            'conversations_created': counters['conversations_created'],
            'conversations_updated': counters['conversations_updated'],
            'messages_created': counters['messages_created'],
            'messages_updated': counters['messages_updated'],
            'result_status': 'SUCCESS_WITH_ERRORS' if counters['conversations_failed'] else 'SUCCESS',
            'elapsed_seconds': round(elapsed_seconds, 3),
            'average_detail_seconds': round(average_detail_seconds, 3) if average_detail_seconds is not None else None,
            'remaining_count': self._remaining_count(
                total_conversations_available=total_conversations_available,
                max_conversations=max_conversations,
                conversations_processed=counters['conversations_processed'] + counters['conversations_failed'],
            ),
        }

    def _failed_conversation(
        self,
        *,
        conversation_id: str,
        conversation_type: str,
        status_code: int | None,
        error_message: str,
    ) -> dict:
        return {
            'conversation_id': conversation_id,
            'conversation_type': conversation_type,
            'status_code': status_code,
            'error_message': error_message,
        }

    def _conversation_detail_diagnostic(self, *, conversation_summary: dict, detail_response) -> dict:
        latest_message = conversation_summary.get('latestMessage')
        latest_message = latest_message if isinstance(latest_message, dict) else {}
        return {
            'conversation_id': conversation_summary.get('conversationId'),
            'conversation_type': conversation_summary.get('conversationType'),
            'conversation_status': conversation_summary.get('conversationStatus'),
            'conversation_title': conversation_summary.get('conversationTitle'),
            'reference_type': conversation_summary.get('referenceType'),
            'reference_id': conversation_summary.get('referenceId'),
            'sender_username': latest_message.get('senderUsername') or conversation_summary.get('senderUsername'),
            'recipient_username': latest_message.get('recipientUsername') or conversation_summary.get('recipientUsername'),
            'created_date': latest_message.get('createdDate') or conversation_summary.get('createdDate'),
            'request_url': detail_response.request_url,
            'request_headers': detail_response.request_headers,
        }

    def _find_nested_string(self, payloads: list[dict], keys: set[str]) -> str | None:
        for payload in payloads:
            value = self._find_nested_string_in_payload(payload, keys)
            if value:
                return value
        return None

    def _find_nested_string_in_payload(self, payload: object, keys: set[str]) -> str | None:
        if isinstance(payload, dict):
            for key, value in payload.items():
                if key in keys and isinstance(value, str) and value.strip():
                    return value.strip()
                nested = self._find_nested_string_in_payload(value, keys)
                if nested:
                    return nested
        if isinstance(payload, list):
            for item in payload:
                nested = self._find_nested_string_in_payload(item, keys)
                if nested:
                    return nested
        return None

    # In ebay_sync_service.py, update the message processing logic

    def _process_message_with_offer(self, message_data: dict, conversation) -> dict:
        """
        Process a message that might contain offer data.
        """
        # Check if this message is about an offer
        if 'offer' in message_data:
            offer_data = message_data['offer']
            
            # If this is a seller offer, create a message with the offer data
            if offer_data.get('type') == 'SELLER_OFFER':
                return {
                    'body': offer_data.get('message', f"Seller sent an offer: ${offer_data.get('amount')}"),
                    'is_inbound': False,
                    'sender_type': 'SELLER',
                    'offer_data': {
                        'type': 'SELLER_OFFER',
                        'amount': float(offer_data.get('amount', 0)),
                        'status': offer_data.get('status', 'PENDING'),
                        'currency': offer_data.get('currency', 'USD'),
                        'message': offer_data.get('message', ''),
                    }
                }
            elif offer_data.get('type') == 'BUYER_OFFER':
                return {
                    'body': offer_data.get('message', f"Buyer sent an offer: ${offer_data.get('amount')}"),
                    'is_inbound': True,
                    'sender_type': 'BUYER',
                    'offer_data': {
                        'type': 'BUYER_OFFER',
                        'amount': float(offer_data.get('amount', 0)),
                        'status': offer_data.get('status', 'PENDING'),
                        'currency': offer_data.get('currency', 'USD'),
                        'message': offer_data.get('message', ''),
                    }
                }
        
        # Regular message
        return {
            'body': message_data.get('text', ''),
            'is_inbound': message_data.get('fromRole') != 'SELLER',
            'sender_type': message_data.get('fromRole', 'BUYER'),
            'offer_data': None
        }

    def _normalize_provider(self) -> str:
        """Return normalized provider name (uppercase)."""
        return EBAY_PROVIDER_NAME.upper()  # 'EBAY'

    # Then update the progress_metadata to include normalized provider
