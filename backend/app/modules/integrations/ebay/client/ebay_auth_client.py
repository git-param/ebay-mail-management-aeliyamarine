import base64
import json
import logging
from dataclasses import dataclass
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from fastapi import HTTPException, status


logger = logging.getLogger(__name__)

EBAY_OAUTH_SCOPES = ['https://api.ebay.com/oauth/api_scope/commerce.message']


@dataclass(frozen=True)
class EbayTokenPayload:
    access_token: str
    refresh_token: str | None
    expires_in: int | None
    refresh_token_expires_in: int | None


class EbayAuthClient:
    def __init__(
        self,
        *,
        client_id: str,
        client_secret: str,
        redirect_uri: str,
        runame: str,
        environment: str,
    ):
        self.client_id = client_id
        self.client_secret = client_secret
        self.redirect_uri = redirect_uri
        self.runame = runame
        self.environment = environment.upper()
        if not self.client_id or not self.client_secret or not self.oauth_redirect_uri:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail='eBay OAuth configuration is incomplete',
            )

    @property
    def oauth_redirect_uri(self) -> str:
        return self.runame or self.redirect_uri

    @property
    def authorization_base_url(self) -> str:
        if self.environment == 'PRODUCTION':
            return 'https://auth.ebay.com/oauth2/authorize'
        return 'https://auth.sandbox.ebay.com/oauth2/authorize'

    @property
    def token_url(self) -> str:
        if self.environment == 'PRODUCTION':
            return 'https://api.ebay.com/identity/v1/oauth2/token'
        return 'https://api.sandbox.ebay.com/identity/v1/oauth2/token'

    def build_authorization_url(self, *, state: str) -> str:
        query = urlencode(
            {
                'client_id': self.client_id,
                'redirect_uri': self.oauth_redirect_uri,
                'response_type': 'code',
                'state': state,
                'scope': ' '.join(EBAY_OAUTH_SCOPES),
            }
        )
        return f'{self.authorization_base_url}?{query}'

    def exchange_code_for_tokens(self, code: str) -> EbayTokenPayload:
        return self._request_tokens(
            {
                'grant_type': 'authorization_code',
                'code': code,
                'redirect_uri': self.oauth_redirect_uri,
            }
        )

    def refresh_access_token(self, refresh_token: str) -> EbayTokenPayload:
        return self._request_tokens(
            {
                'grant_type': 'refresh_token',
                'refresh_token': refresh_token,
                'scope': ' '.join(EBAY_OAUTH_SCOPES),
            }
        )

    def _request_tokens(self, payload: dict[str, str]) -> EbayTokenPayload:
        body = urlencode(payload).encode('utf-8')
        credentials = base64.b64encode(f'{self.client_id}:{self.client_secret}'.encode('utf-8')).decode('ascii')
        request = Request(
            self.token_url,
            data=body,
            headers={
                'Authorization': f'Basic {credentials}',
                'Content-Type': 'application/x-www-form-urlencoded',
                'Accept': 'application/json',
            },
            method='POST',
        )
        try:
            with urlopen(request, timeout=20) as response:
                data = json.loads(response.read().decode('utf-8'))
        # except HTTPError as exc:
        #     logger.warning('eBay OAuth token exchange failed with HTTP status %s', exc.code)
        #     raise HTTPException(
        #         status_code=status.HTTP_502_BAD_GATEWAY,
        #         detail='eBay OAuth token exchange failed',
        #     ) from exc

        except HTTPError as exc:
            error_body = ""

            try:
                error_body = exc.read().decode("utf-8")
            except Exception:
                pass

            logger.error(
                "eBay OAuth token exchange failed. Status=%s Body=%s",
                exc.code,
                error_body,
            )

            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail="eBay OAuth token exchange failed",
            ) from exc

        except (URLError, TimeoutError, json.JSONDecodeError) as exc:
            logger.warning('Unable to reach or parse eBay OAuth token service response')
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail='Unable to reach eBay OAuth service',
            ) from exc

        access_token = data.get('access_token')
        if not access_token:
            logger.warning('eBay OAuth token response did not include an access token')
            raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail='eBay OAuth response was invalid')

        logger.info('eBay OAuth token request succeeded')

        return EbayTokenPayload(
            access_token=access_token,
            refresh_token=data.get('refresh_token'),
            expires_in=data.get('expires_in'),
            refresh_token_expires_in=data.get('refresh_token_expires_in'),
        )
