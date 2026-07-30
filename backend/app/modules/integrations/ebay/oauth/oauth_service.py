import secrets
import logging
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models.ebay_account import EbayAccount, EbayConnectionStatus
from app.modules.integrations.ebay.client.ebay_auth_client import EbayAuthClient


logger = logging.getLogger(__name__)


class EbayOAuthService:
    def __init__(self, db: Session):
        self.db = db
        self.settings = get_settings()
        self.client = EbayAuthClient(
            client_id=self.settings.ebay_client_id,
            client_secret=self.settings.ebay_client_secret,
            redirect_uri=self.settings.ebay_redirect_uri,
            runame=self.settings.ebay_runame,
            environment=self.settings.ebay_environment,
            media_base_url=self.settings.ebay_media_base_url,
        )

    def create_authorization_url(self, account_id: UUID) -> tuple[str, str]:
        account = self.db.get(EbayAccount, account_id)
        if not account:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='eBay account not found')

        state = secrets.token_urlsafe(32)
        account.oauth_state = state
        account.connection_status = EbayConnectionStatus.PENDING
        self.db.commit()

        authorization_url = self.client.build_authorization_url(state=state)
        logger.warning('Generated eBay OAuth authorization URL for account %s', account.id)
        return authorization_url, state
