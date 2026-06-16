import logging

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models.ebay_account import EbayAccount, EbayConnectionStatus
from app.modules.integrations.ebay.client.ebay_auth_client import EbayAuthClient
from app.modules.integrations.ebay.oauth.token_service import EbayTokenService
from urllib.parse import unquote



logger = logging.getLogger(__name__)


class EbayOAuthCallbackService:
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

    def handle_callback(self, *, code: str | None, state: str | None, error: str | None = None) -> EbayAccount:
        logger.info('Received eBay OAuth callback')
        account = self._get_account_by_state(state)
        if error:
            account.connection_status = EbayConnectionStatus.FAILED
            account.oauth_state = None
            self.db.commit()
            logger.warning('eBay OAuth callback failed for account %s', account.id)
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail='eBay authorization was denied')

        if not code:
            account.connection_status = EbayConnectionStatus.FAILED
            account.oauth_state = None
            self.db.commit()
            logger.warning('eBay OAuth callback missing authorization code for account %s', account.id)
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail='Authorization code is missing')

        try:            
            decoded_code = unquote(code)
            token_payload = self.client.exchange_code_for_tokens(decoded_code)

            connected_account = EbayTokenService(self.db).store_tokens(account, token_payload)
            logger.info('eBay OAuth callback token exchange succeeded for account %s', account.id)
            return connected_account
        except HTTPException:
            account.connection_status = EbayConnectionStatus.FAILED
            account.oauth_state = None
            self.db.commit()
            logger.warning('eBay OAuth callback token exchange failed for account %s', account.id)
            raise

    def _get_account_by_state(self, state: str | None) -> EbayAccount:
        if not state:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail='OAuth state is missing')

        account = self.db.scalar(select(EbayAccount).where(EbayAccount.oauth_state == state))
        if not account:
            logger.warning('eBay OAuth callback received invalid state')
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail='OAuth state is invalid or expired')
        return account
