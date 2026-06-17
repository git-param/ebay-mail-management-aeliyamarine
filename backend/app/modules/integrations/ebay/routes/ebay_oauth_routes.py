import logging
from datetime import UTC, datetime
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from app.api.dependencies import get_current_user
from app.db.session import get_db
from app.models.ebay_account import EbayAccount
from app.modules.integrations.ebay.oauth.callback_service import EbayOAuthCallbackService
from app.modules.integrations.ebay.oauth.oauth_service import EbayOAuthService
from app.modules.integrations.ebay.oauth.token_service import EbayTokenService
from app.modules.integrations.ebay.schemas.oauth_schemas import (
    EbayConnectRequest,
    EbayConnectResponse,
    EbayOAuthCallbackResponse,
    EbayRefreshTokenResponse,
    EbayTestConnectionResponse,
)


logger = logging.getLogger(__name__)
router = APIRouter()


def require_admin(current_user=Depends(get_current_user)):
    if current_user.role.name != 'Admin':
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail='Only admins can connect eBay accounts')
    return current_user


@router.post('/connect', response_model=EbayConnectResponse)
def connect_ebay_account(
    payload: EbayConnectRequest,
    db: Session = Depends(get_db),
    current_user=Depends(require_admin),
) -> EbayConnectResponse:
    authorization_url, state = EbayOAuthService(db).create_authorization_url(payload.account_id)
    return EbayConnectResponse(authorization_url=authorization_url, state=state)


@router.get('/callback', response_model=EbayOAuthCallbackResponse)
def handle_ebay_oauth_callback(
    code: str | None = Query(default=None),
    state: str | None = Query(default=None),
    error: str | None = Query(default=None),
    db: Session = Depends(get_db),
) -> EbayOAuthCallbackResponse:
    account = EbayOAuthCallbackService(db).handle_callback(code=code, state=state, error=error)
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
    logger.info(
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
    logger.info(
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
