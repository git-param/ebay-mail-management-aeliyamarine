from datetime import UTC, datetime, timedelta
import logging
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models.ebay_account import EbayAccount, EbayConnectionStatus
from app.modules.integrations.ebay.client.ebay_auth_client import EbayAuthClient, EbayTokenPayload


logger = logging.getLogger(__name__)


class EbayTokenService:
    def __init__(self, db: Session):
        self.db = db
        self.settings = get_settings()
        self.client = EbayAuthClient(
            client_id=self.settings.ebay_client_id,
            client_secret=self.settings.ebay_client_secret,
            redirect_uri=self.settings.ebay_redirect_uri,
            runame=self.settings.ebay_runame,
            environment=self.settings.ebay_environment,
        )

    def store_tokens(self, account: EbayAccount, token_payload: EbayTokenPayload) -> EbayAccount:
        now = datetime.now(UTC)
        access_token_expires_at = self._expires_at(token_payload.expires_in, now)
        refresh_token_expires_at = self._expires_at(token_payload.refresh_token_expires_in, now)

        account.access_token = token_payload.access_token
        if token_payload.refresh_token:
            account.refresh_token = token_payload.refresh_token
        account.access_token_expires_at = access_token_expires_at
        account.token_expires_at = access_token_expires_at
        if refresh_token_expires_at:
            account.refresh_token_expires_at = refresh_token_expires_at
        account.connection_status = EbayConnectionStatus.CONNECTED
        account.last_connected_at = now
        account.oauth_state = None
        self.db.commit()
        self.db.refresh(account)
        logger.info('Stored eBay OAuth tokens for account %s', account.id)
        return account

    def refresh_access_token(self, account_id: UUID) -> EbayAccount:
        account = self.db.get(EbayAccount, account_id)
        if not account:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='eBay account not found')
        if not account.refresh_token:
            account.connection_status = EbayConnectionStatus.EXPIRED
            self.db.commit()
            logger.warning('eBay refresh token unavailable for account %s', account.id)
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail='Refresh token is not available')

        try:
            token_payload = self.client.refresh_access_token(account.refresh_token)
            refreshed_account = self.store_tokens(account, token_payload)
            logger.info('eBay access token refresh succeeded for account %s', account.id)
            return refreshed_account
        except HTTPException:
            logger.warning('eBay access token refresh failed for account %s', account.id)
            raise

    def test_connection(self, account_id: UUID) -> EbayAccount:
        account = self.db.get(EbayAccount, account_id)
        if not account:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='eBay account not found')
        if not account.access_token:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail='eBay account has no access token')
        if account.connection_status != EbayConnectionStatus.CONNECTED:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f'eBay account is not connected. Current status: {account.connection_status.value}',
            )
        if account.access_token_expires_at and account.access_token_expires_at <= datetime.now(UTC):
            account.connection_status = EbayConnectionStatus.EXPIRED
            self.db.commit()
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail='eBay access token has expired')
        return account

    def _expires_at(self, expires_in: int | None, base_time: datetime) -> datetime | None:
        if not expires_in:
            return None
        return base_time + timedelta(seconds=int(expires_in))
