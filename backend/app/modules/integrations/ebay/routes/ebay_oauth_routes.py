from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.api.dependencies import get_current_user
from app.db.session import get_db
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
