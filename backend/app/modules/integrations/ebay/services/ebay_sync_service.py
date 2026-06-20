import logging
from dataclasses import dataclass
from datetime import UTC, datetime
from time import perf_counter
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.conversation import SyncLogStatus
from app.models.ebay_account import EbayAccount, EbayConnectionStatus
from app.modules.integrations.ebay.oauth.token_service import EbayTokenService
from app.modules.integrations.ebay.providers import EBAY_PROVIDER_NAME
from app.modules.integrations.ebay.services.ebay_message_service import EbayMessageService
from app.services.ebay_api_usage_service import EbayApiUsageService
from app.services.sync_log_service import SyncLogService


logger = logging.getLogger(__name__)

EBAY_MESSAGE_SYNC_TYPE = 'EBAY_MESSAGE_SYNC'


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

    def sync_account(self, account_id: UUID, *, max_conversations: int | None = None) -> EbaySyncResult:
        account = self._get_syncable_account(account_id)
        # if reserve_api_usage:
        self.api_usage_service.reserve_calls(1)

        sync_log = self.sync_log_service.start_sync(
            provider=EBAY_PROVIDER_NAME,
            provider_account_id=account.id,
            sync_type=EBAY_MESSAGE_SYNC_TYPE,
            sync_metadata={'conversation_type': 'FROM_MEMBERS', 'max_conversations': max_conversations},
        )
        counters = {
            'conversations_processed': 0,
            'conversations_failed': 0,
            'conversations_created': 0,
            'conversations_updated': 0,
            'messages_created': 0,
            'messages_updated': 0,
        }
        failed_conversations: list[dict] = []
        total_conversations_available = None
        detail_seconds_total = 0.0
        sync_started_at = perf_counter()

        try:
            account = self._ensure_access_token(account)
            for conversation_summary, page_total in self._iter_conversation_summaries(
                account.access_token,
                max_conversations=max_conversations,
            ):
                if page_total is not None:
                    total_conversations_available = page_total
                conversation_id = self._conversation_id(conversation_summary)
                if not conversation_id:
                    logger.warning('Skipping eBay conversation without conversationId for account %s', account.id)
                    continue

                conversation_type = self._conversation_type(conversation_summary)
                detail_started_at = perf_counter()
                detail_response = self.token_service.client.get_conversation_raw(
                    account.access_token,
                    conversation_id=conversation_id,
                    conversation_type=conversation_type,
                    limit=50,
                    offset=0,
                )
                logger.info(
                    'eBay conversation detail diagnostic account_id=%s conversation_id=%s conversation_type=%s request_url=%s conversation_summary=%s',
                    account.id,
                    conversation_id,
                    conversation_type,
                    detail_response.request_url,
                    conversation_summary,
                )
                if conversation_id == '112795218410' or not detail_response.ok:
                    logger.warning(
                        'eBay conversation detail response diagnostic account_id=%s conversation_id=%s conversation_type=%s status_code=%s request_url=%s response_body=%s conversation_summary=%s',
                        account.id,
                        conversation_id,
                        conversation_type,
                        detail_response.status_code,
                        detail_response.request_url,
                        detail_response.payload,
                        conversation_summary,
                    )
                if not detail_response.ok or not isinstance(detail_response.payload, dict):
                    failed_conversation = self._failed_conversation(
                        conversation_id=conversation_id,
                        conversation_type=conversation_type,
                        status_code=detail_response.status_code,
                        error_message='eBay conversation detail request failed',
                    )
                    failed_conversation['response_body'] = detail_response.payload
                    failed_conversations.append(failed_conversation)
                    counters['conversations_failed'] += 1
                    logger.warning(
                        'Skipping failed eBay conversation detail account_id=%s conversation_id=%s conversation_type=%s status_code=%s response_body=%s',
                        account.id,
                        conversation_id,
                        conversation_type,
                        detail_response.status_code,
                        detail_response.payload,
                    )
                    continue

                try:
                    with self.db.begin_nested():
                        conversation_detail = detail_response.payload
                        detail_elapsed_seconds = perf_counter() - detail_started_at
                        detail_seconds_total += detail_elapsed_seconds
                        conversation, created = self.message_service.upsert_conversation(
                            account=account,
                            conversation_summary=conversation_summary,
                            conversation_detail=conversation_detail,
                            conversation_type=conversation_type,
                        )
                        self.db.flush()
                        messages_created, messages_updated = self.message_service.upsert_messages(
                            account=account,
                            conversation=conversation,
                            conversation_detail=conversation_detail,
                        )
                        counters['conversations_processed'] += 1
                        if created:
                            counters['conversations_created'] += 1
                        else:
                            counters['conversations_updated'] += 1
                        counters['messages_created'] += messages_created
                        counters['messages_updated'] += messages_updated
                except Exception as conversation_exc:
                    failed_conversations.append(
                        self._failed_conversation(
                            conversation_id=conversation_id,
                            conversation_type=conversation_type,
                            status_code=None,
                            error_message=str(conversation_exc),
                        )
                    )
                    counters['conversations_failed'] += 1
                    logger.exception(
                        'Skipping eBay conversation after processing failure account_id=%s conversation_id=%s conversation_type=%s',
                        account.id,
                        conversation_id,
                        conversation_type,
                    )
                    continue

                elapsed_seconds = perf_counter() - sync_started_at
                remaining_count = self._remaining_count(
                    total_conversations_available=total_conversations_available,
                    max_conversations=max_conversations,
                    conversations_processed=counters['conversations_processed'] + counters['conversations_failed'],
                )
                logger.info(
                    'eBay sync progress account_id=%s processed=%s current_conversation_id=%s elapsed_seconds=%.2f remaining_count=%s detail_seconds=%.2f',
                    account.id,
                    counters['conversations_processed'],
                    conversation_id,
                    elapsed_seconds,
                    remaining_count,
                    detail_elapsed_seconds,
                )

                if counters['conversations_processed'] % 25 == 0:
                    self.sync_log_service.update_progress(
                        sync_log.id,
                        records_processed=self._records_processed(counters),
                        sync_metadata=self._progress_metadata(
                            counters=counters,
                            total_conversations_available=total_conversations_available,
                            max_conversations=max_conversations,
                            elapsed_seconds=elapsed_seconds,
                            detail_seconds_total=detail_seconds_total,
                            failed_conversations=failed_conversations,
                        ),
                    )

            account.last_sync_at = datetime.now(UTC)
            account.sync_status = 'SUCCESS_WITH_ERRORS' if counters['conversations_failed'] else 'SUCCESS'
            elapsed_seconds = perf_counter() - sync_started_at
            sync_log = self.sync_log_service.complete_sync(
                sync_log.id,
                records_processed=self._records_processed(counters),
            )
            if counters['conversations_failed']:
                sync_log.error_message = f"{counters['conversations_failed']} conversation(s) failed during sync"
            sync_log.sync_metadata = {
                **(sync_log.sync_metadata or {}),
                **self._progress_metadata(
                    counters=counters,
                    total_conversations_available=total_conversations_available,
                    max_conversations=max_conversations,
                    elapsed_seconds=elapsed_seconds,
                    detail_seconds_total=detail_seconds_total,
                    failed_conversations=failed_conversations,
                ),
            }
            self.db.commit()
            logger.info(
                'eBay message sync succeeded account_id=%s conversations=%s messages_created=%s messages_updated=%s elapsed_seconds=%.2f average_detail_seconds=%.2f',
                account.id,
                counters['conversations_processed'],
                counters['messages_created'],
                counters['messages_updated'],
                elapsed_seconds,
                self._average_detail_seconds(detail_seconds_total, counters['conversations_processed']) or 0,
            )
            return self._build_result(
                account=account,
                sync_log_id=sync_log.id,
                status=account.sync_status,
                counters=counters,
                failed_conversations=failed_conversations,
                total_conversations_available=total_conversations_available,
                elapsed_seconds=elapsed_seconds,
                average_detail_seconds=self._average_detail_seconds(
                    detail_seconds_total,
                    counters['conversations_processed'],
                ),
            )
        except Exception as exc:
            self.db.rollback()
            failed_sync_log = self.sync_log_service.fail_sync(sync_log.id, str(exc))
            account = self.db.get(EbayAccount, account.id)
            if account:
                account.sync_status = 'FAILED'
                self.db.commit()
            logger.exception('eBay message sync failed for account %s', account_id)
            return self._build_result(
                account=account or self._get_syncable_account(account_id),
                sync_log_id=failed_sync_log.id,
                status=failed_sync_log.status.value,
                counters=counters,
                failed_conversations=failed_conversations,
                total_conversations_available=total_conversations_available,
                elapsed_seconds=perf_counter() - sync_started_at,
                average_detail_seconds=self._average_detail_seconds(
                    detail_seconds_total,
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
        self.api_usage_service.reserve_calls(len(accounts))
        return [self.sync_account(account.id, reserve_api_usage=False) for account in accounts]

    def _iter_conversation_summaries(self, access_token: str, *, max_conversations: int | None = None):
        limit = 50
        offset = 0
        yielded_count = 0
        while True:
            payload = self.token_service.client.get_conversations(
                access_token,
                conversation_type='FROM_MEMBERS',
                limit=limit,
                offset=offset,
            )
            total = payload.get('total')
            page_total = total if isinstance(total, int) else None
            conversations = payload.get('conversations') if isinstance(payload.get('conversations'), list) else []
            logger.info(
                'eBay conversation list page fetched offset=%s limit=%s page_count=%s total_available=%s max_conversations=%s',
                offset,
                limit,
                len(conversations),
                page_total,
                max_conversations,
            )
            for conversation in conversations:
                if isinstance(conversation, dict):
                    yield conversation, page_total
                    yielded_count += 1
                    if max_conversations and yielded_count >= max_conversations:
                        return

            if not conversations:
                break
            offset += limit
            if page_total is not None and offset >= page_total:
                break

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
        elapsed_seconds: float,
        detail_seconds_total: float,
        failed_conversations: list[dict],
    ) -> dict:
        average_detail_seconds = self._average_detail_seconds(
            detail_seconds_total,
            counters['conversations_processed'],
        )
        return {
            'conversation_type': 'FROM_MEMBERS',
            'max_conversations': max_conversations,
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
