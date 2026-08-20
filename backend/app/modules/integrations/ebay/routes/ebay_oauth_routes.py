import logging
from datetime import UTC, datetime, timedelta
from urllib.parse import quote
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import JSONResponse, RedirectResponse
from sqlalchemy.orm import Session
from sqlalchemy import func, select

from app.api.dependencies import get_current_user
from app.core.config import get_settings
from app.db.session import get_db
from app.models.conversation import SyncLog
from app.models.ebay_account import EbayAccount, EbayConnectionStatus
from app.modules.integrations.ebay.oauth.callback_service import EbayOAuthCallbackService
from app.modules.integrations.ebay.oauth.oauth_service import EbayOAuthService
from app.modules.integrations.ebay.oauth.token_service import EbayTokenService
from app.modules.integrations.ebay.schemas.oauth_schemas import (
    EbayConnectRequest,
    EbayConnectResponse,
    EbayApiUsageListResponse,
    EbayAutoSyncStatusResponse,
    EbayAutoSyncToggleRequest,
    EbayManualCallbackRequest,
    EbayApiUsageResponse,
    EbayOAuthCallbackResponse,
    EbayRefreshTokenResponse,
    EbaySyncAllResponse,
    EbaySyncResultResponse,
    EbayTestConnectionResponse,
)
from app.modules.integrations.ebay.services.ebay_sync_service import EbaySyncResult, EbaySyncService
from app.modules.config_management.service import ConfigService
from app.services.ebay_auto_sync_service import AUTO_SYNC_ENABLED_KEY, AUTO_SYNC_INTERVAL_KEY
from app.services.audit_service import AuditService
from app.services.ebay_api_usage_service import EbayApiUsageService, EbayApiUsageSummary
from app.services.ebay_sync_worker import spawn_ebay_sync_processes


logger = logging.getLogger(__name__)
router = APIRouter()


def require_admin(current_user=Depends(get_current_user)):
    if current_user.role.name != 'Admin':
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail='Only admins can connect eBay accounts')
    return current_user


def require_ebay_sync_access(current_user=Depends(get_current_user)):
    if current_user.role.name != 'Admin':
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail='Only admins can sync eBay accounts')
    return current_user


@router.post('/connect', response_model=EbayConnectResponse)
def connect_ebay_account(
    payload: EbayConnectRequest,
    db: Session = Depends(get_db),
    current_user=Depends(require_admin),
) -> EbayConnectResponse:
    authorization_url, state = EbayOAuthService(db).create_authorization_url(payload.account_id)
    AuditService(db).log(
        action='EBAY_CONNECT_LINK_GENERATED',
        user_id=current_user.id,
        entity_type='EBAY_ACCOUNT',
        entity_id=payload.account_id,
        category='EBAY',
    )
    db.commit()
    return EbayConnectResponse(authorization_url=authorization_url, state=state)


@router.post('/manual-callback', response_model=EbayOAuthCallbackResponse)
def submit_manual_ebay_callback(
    payload: EbayManualCallbackRequest,
    db: Session = Depends(get_db),
    current_user=Depends(require_admin),
) -> EbayOAuthCallbackResponse:
    account = EbayOAuthCallbackService(db).handle_callback(code=payload.code, state=payload.state, error=None)
    AuditService(db).log(
        action='EBAY_MANUAL_CALLBACK_SUBMITTED',
        user_id=current_user.id,
        entity_type='EBAY_ACCOUNT',
        entity_id=account.id,
        category='EBAY',
    )
    db.commit()
    return EbayOAuthCallbackResponse(
        account_id=account.id,
        connection_status=account.connection_status.value,
        ebay_username=account.ebay_username,
        ebay_user_id=account.ebay_user_id,
        seller_account_id=account.ebay_user_id,
        store_name=account.store_name,
        access_token_expires_at=account.access_token_expires_at,
        refresh_token_expires_at=account.refresh_token_expires_at,
        message='eBay account connected successfully',
    )


@router.get('/callback')
def handle_ebay_oauth_callback(
    code: str | None = Query(default=None),
    state: str | None = Query(default=None),
    error: str | None = Query(default=None),
    db: Session = Depends(get_db),
) -> RedirectResponse:
    settings = get_settings()
    try:
        account = EbayOAuthCallbackService(db).handle_callback(code=code, state=state, error=error)
    except HTTPException as exc:
        return RedirectResponse(
            f'{settings.frontend_url}/ebay-accounts?ebay_connection=failed&message={quote(str(exc.detail))}',
            status_code=status.HTTP_303_SEE_OTHER,
        )

    response = EbayOAuthCallbackResponse(
        account_id=account.id,
        connection_status=account.connection_status.value,
        ebay_username=account.ebay_username,
        ebay_user_id=account.ebay_user_id,
        seller_account_id=account.ebay_user_id,
        store_name=account.store_name,
        access_token_expires_at=account.access_token_expires_at,
        refresh_token_expires_at=account.refresh_token_expires_at,
        message='eBay account connected successfully',
    )
    return RedirectResponse(
        f'{settings.frontend_url}/ebay-accounts?ebay_connection=success&account_id={response.account_id}',
        status_code=status.HTTP_303_SEE_OTHER,
    )


@router.post('/refresh-token/{account_id}', response_model=EbayRefreshTokenResponse)
def refresh_ebay_access_token(
    account_id: UUID,
    db: Session = Depends(get_db),
    current_user=Depends(require_admin),
) -> EbayRefreshTokenResponse:
    account = EbayTokenService(db).refresh_access_token(account_id)
    return EbayRefreshTokenResponse(
        account_id=account.id,
        connection_status=account.connection_status.value,
        access_token_expires_at=account.access_token_expires_at,
        message='eBay access token refreshed successfully',
    )


@router.get('/test-connection/{account_id}', response_model=EbayTestConnectionResponse)
def test_ebay_connection(
    account_id: UUID,
    db: Session = Depends(get_db),
    current_user=Depends(require_admin),
) -> EbayTestConnectionResponse:
    account = EbayTokenService(db).test_connection(account_id)
    return EbayTestConnectionResponse(
        connected=True,
        account_status=account.connection_status.value,
        account_id=account.id,
        access_token_expires_at=account.access_token_expires_at,
    )


def serialize_api_usage(usage: EbayApiUsageSummary) -> EbayApiUsageResponse:
    return EbayApiUsageResponse(
        usage_date=usage.usage_date.isoformat(),
        api_name=usage.api_name,
        call_count=usage.call_count,
        daily_limit=usage.daily_limit,
        remaining=usage.remaining,
    )


@router.get('/api-usage', response_model=EbayApiUsageListResponse)
def get_ebay_api_usage(
    db: Session = Depends(get_db),
    current_user=Depends(require_ebay_sync_access),
) -> EbayApiUsageListResponse:
    return EbayApiUsageListResponse(
        items=[serialize_api_usage(usage) for usage in EbayApiUsageService(db).get_today_usage_all()]
    )


def auto_sync_status(db: Session) -> EbayAutoSyncStatusResponse:
    config = ConfigService(db)
    enabled = config.get_bool(AUTO_SYNC_ENABLED_KEY, False)
    interval_hours = max(config.get_int(AUTO_SYNC_INTERVAL_KEY, 6), 1)
    latest_sync_at = db.scalar(
        select(func.max(EbayAccount.last_sync_at))
        .where(EbayAccount.connection_status == EbayConnectionStatus.CONNECTED)
        .where(EbayAccount.is_active.is_(True))
    )
    if latest_sync_at and latest_sync_at.tzinfo is None:
        latest_sync_at = latest_sync_at.replace(tzinfo=UTC)
    next_run_at = latest_sync_at + timedelta(hours=interval_hours) if latest_sync_at else None
    return EbayAutoSyncStatusResponse(
        enabled=enabled,
        interval_hours=interval_hours,
        latest_sync_at=latest_sync_at,
        next_run_at=next_run_at,
    )


@router.get('/auto-sync', response_model=EbayAutoSyncStatusResponse)
def get_ebay_auto_sync_status(
    db: Session = Depends(get_db),
    current_user=Depends(require_ebay_sync_access),
) -> EbayAutoSyncStatusResponse:
    _ = current_user
    return auto_sync_status(db)


@router.patch('/auto-sync', response_model=EbayAutoSyncStatusResponse)
def set_ebay_auto_sync_status(
    payload: EbayAutoSyncToggleRequest,
    db: Session = Depends(get_db),
    current_user=Depends(require_ebay_sync_access),
) -> EbayAutoSyncStatusResponse:
    ConfigService(db).set_value(AUTO_SYNC_ENABLED_KEY, 'true' if payload.enabled else 'false', current_user)
    AuditService(db).log(
        action='EBAY_AUTO_SYNC_ENABLED' if payload.enabled else 'EBAY_AUTO_SYNC_DISABLED',
        user_id=current_user.id,
        entity_type='EBAY_AUTO_SYNC',
        category='SYNC',
        metadata={'enabled': payload.enabled},
    )
    db.commit()
    return auto_sync_status(db)


def serialize_sync_result(
    result: EbaySyncResult,
    api_usage: EbayApiUsageSummary | None = None,
) -> EbaySyncResultResponse:
    return EbaySyncResultResponse(
        account_id=result.account_id,
        ebay_username=result.ebay_username,
        sync_log_id=result.sync_log_id,
        status=result.status,
        conversations_processed=result.conversations_processed,
        conversations_failed=result.conversations_failed,
        failed_conversation_ids=result.failed_conversation_ids,
        conversations_created=result.conversations_created,
        conversations_updated=result.conversations_updated,
        messages_created=result.messages_created,
        messages_updated=result.messages_updated,
        total_conversations_available=result.total_conversations_available,
        elapsed_seconds=result.elapsed_seconds,
        average_detail_seconds=result.average_detail_seconds,
        error_message=result.error_message,
        api_usage=serialize_api_usage(api_usage) if api_usage else None,
    )


def _queued_sync_result(account: EbayAccount, sync_log: SyncLog) -> EbaySyncResult:
    """Build the immediate API response for a sync that has been handed to a worker."""
    return EbaySyncResult(
        account_id=account.id,
        ebay_username=account.ebay_username,
        sync_log_id=sync_log.id,
        status='RUNNING',
        conversations_processed=0,
        conversations_failed=0,
        failed_conversation_ids=[],
        conversations_created=0,
        conversations_updated=0,
        messages_created=0,
        messages_updated=0,
        total_conversations_available=None,
        elapsed_seconds=0.0,
        average_detail_seconds=None,
        error_message=None,
    )


def _start_queued_syncs(
    jobs: list[tuple[EbayAccount, SyncLog]],
) -> list[EbaySyncResult]:
    """Spawn worker processes after their SyncLog rows are committed."""
    if not jobs:
        return []

    try:
        pids = spawn_ebay_sync_processes(
            [
                (account.id, sync_log.id, None)
                for account, sync_log in jobs
            ]
        )
    except Exception as exc:
        logger.exception('Could not start eBay sync worker process(es)')
        # The reservation was committed before process.start(). If process
        # creation fails, immediately release every reserved job so the
        # account cannot remain stuck in SYNCING/RUNNING forever.
        for account, sync_log in jobs:
            try:
                sync_log_service = EbaySyncService(db=None)  # replaced below
            except Exception:
                pass
        raise

    logger.warning(
        'eBay sync worker process(es) started jobs=%s pids=%s',
        len(jobs),
        pids,
    )
    return [_queued_sync_result(account, sync_log) for account, sync_log in jobs]


@router.post('/sync/{account_id}', response_model=EbaySyncResultResponse)
def sync_ebay_account(
    account_id: UUID,
    max_conversations: int | None = Query(default=None, ge=1, le=100),
    db: Session = Depends(get_db),
    current_user=Depends(require_ebay_sync_access),
) -> EbaySyncResultResponse:
    sync_service = EbaySyncService(db)
    sync_log = sync_service.queue_sync_account(
        account_id,
        max_conversations=max_conversations,
        trigger='MANUAL',
    )
    account = db.get(EbayAccount, account_id)
    if not account:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail='eBay account not found after sync reservation',
        )

    try:
        pids = spawn_ebay_sync_processes(
            [(account.id, sync_log.id, max_conversations)]
        )
    except Exception as exc:
        logger.exception(
            'Failed to start eBay sync worker account_id=%s sync_log_id=%s',
            account.id,
            sync_log.id,
        )
        # The sync reservation is already committed, so cleanly release it.
        db.rollback()
        from app.models.conversation import SyncLogStatus
        from app.services.sync_log_service import SyncLogService

        current_log = db.get(SyncLog, sync_log.id)
        if current_log and current_log.status == SyncLogStatus.RUNNING:
            SyncLogService(db).fail_sync(sync_log.id, f'Worker process could not be started: {exc}')
        account = db.get(EbayAccount, account.id)
        if account:
            account.sync_status = 'FAILED'
            db.commit()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail='eBay sync worker could not be started',
        ) from exc

    logger.warning(
        'Manual eBay sync handed to worker account_id=%s sync_log_id=%s pid=%s',
        account.id,
        sync_log.id,
        pids[0] if pids else None,
    )

    return serialize_sync_result(
        _queued_sync_result(account, sync_log),
    )


@router.post('/sync-all', response_model=EbaySyncAllResponse)
def sync_all_ebay_accounts(
    db: Session = Depends(get_db),
    current_user=Depends(require_ebay_sync_access),
) -> EbaySyncAllResponse:
    sync_service = EbaySyncService(db)
    jobs = sync_service.queue_sync_all_connected_accounts(
        trigger='MANUAL_ALL',
    )

    if not jobs:
        return EbaySyncAllResponse(
            results=[],
            api_usage=EbayApiUsageListResponse(items=[
                serialize_api_usage(item)
                for item in EbayApiUsageService(db).get_today_usage_all()
            ]),
        )

    try:
        pids = spawn_ebay_sync_processes(
            [(account.id, sync_log.id, None) for account, sync_log in jobs]
        )
    except Exception as exc:
        logger.exception(
            'Failed to start one or more eBay sync worker processes for Sync All'
        )
        # If process creation fails before all jobs are handed off, mark all
        # reserved jobs failed rather than leaving stale RUNNING records.
        from app.models.conversation import SyncLogStatus
        from app.services.sync_log_service import SyncLogService

        db.rollback()
        sync_log_service = SyncLogService(db)
        for account, sync_log in jobs:
            current_log = db.get(SyncLog, sync_log.id)
            if current_log and current_log.status == SyncLogStatus.RUNNING:
                sync_log_service.fail_sync(
                    sync_log.id,
                    f'Worker process could not be started: {exc}',
                )
            current_account = db.get(EbayAccount, account.id)
            if current_account:
                current_account.sync_status = 'FAILED'
                db.commit()

        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail='One or more eBay sync workers could not be started',
        ) from exc

    logger.warning(
        'Manual eBay Sync All handed to worker processes jobs=%s pids=%s',
        len(jobs),
        pids,
    )

    usage = EbayApiUsageService(db).get_today_usage_all()
    return EbaySyncAllResponse(
        results=[
            serialize_sync_result(_queued_sync_result(account, sync_log))
            for account, sync_log in jobs
        ],
        api_usage=EbayApiUsageListResponse(
            items=[serialize_api_usage(item) for item in usage]
        ),
    )


@router.get('/sync-status/{sync_log_id}')
def get_ebay_sync_status(
    sync_log_id: UUID,
    db: Session = Depends(get_db),
    current_user=Depends(require_ebay_sync_access),
) -> dict:
    """Return persisted progress for a process-isolated eBay sync job."""
    sync_log = db.get(SyncLog, sync_log_id)
    if not sync_log:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail='eBay sync job not found',
        )

    if sync_log.provider != 'EBAY':
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail='eBay sync job not found',
        )

    account = (
        db.get(EbayAccount, sync_log.provider_account_id)
        if sync_log.provider_account_id
        else None
    )
    metadata = sync_log.sync_metadata or {}

    return {
        'sync_log_id': sync_log.id,
        'account_id': sync_log.provider_account_id,
        'ebay_username': account.ebay_username if account else None,
        'status': sync_log.status.value,
        'account_sync_status': account.sync_status if account else None,
        'started_at': sync_log.started_at,
        'completed_at': sync_log.completed_at,
        'records_processed': sync_log.records_processed,
        'error_message': sync_log.error_message,
        'sync_metadata': metadata,
    }


@router.post('/test-conversations/{account_id}')
def test_ebay_conversations(
    account_id: UUID,
    conversation_type: str = Query(default='FROM_MEMBERS'),
    limit: int = Query(default=10, ge=1, le=50),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
    current_user=Depends(require_admin),
):
    account = db.get(EbayAccount, account_id)
    if not account:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='eBay account not found')

    token_service = EbayTokenService(db)
    if not account.access_token or (
        account.access_token_expires_at and account.access_token_expires_at <= datetime.now(UTC)
    ):
        account = token_service.refresh_access_token(account_id)

    if not account.access_token:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail='eBay account has no access token')

    client = token_service.client
    response = client.get_conversations_raw(
        account.access_token,
        conversation_type=conversation_type,
        limit=limit,
        offset=offset,
    )
    logger.warning(
        'eBay conversation test account_id=%s ebay_username=%s request_url=%s response_status_code=%s',
        account.id,
        account.ebay_username,
        client.conversations_url,
        response.status_code,
    )

    if not response.ok:
        return JSONResponse(status_code=response.status_code, content=response.payload)
    return response.payload


@router.get('/test-conversation/{account_id}/{conversation_id}')
def test_ebay_conversation(
    account_id: UUID,
    conversation_id: str,
    conversation_type: str = Query(default='FROM_MEMBERS'),
    limit: int = Query(default=25, ge=1, le=50),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
    current_user=Depends(require_admin),
):
    account = db.get(EbayAccount, account_id)
    if not account:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='eBay account not found')

    token_service = EbayTokenService(db)
    if not account.access_token or (
        account.access_token_expires_at and account.access_token_expires_at <= datetime.now(UTC)
    ):
        account = token_service.refresh_access_token(account_id)

    if not account.access_token:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail='eBay account has no access token')

    client = token_service.client
    response = client.get_conversation_raw(
        account.access_token,
        conversation_id=conversation_id,
        conversation_type=conversation_type,
        limit=limit,
        offset=offset,
    )
    logger.warning(
        'eBay conversation detail test account_id=%s ebay_username=%s conversation_id=%s request_url=%s response_status_code=%s',
        account.id,
        account.ebay_username,
        conversation_id,
        f'{client.conversations_url}/{conversation_id}',
        response.status_code,
    )

    if not response.ok:
        return JSONResponse(status_code=response.status_code, content=response.payload)
    return response.payload