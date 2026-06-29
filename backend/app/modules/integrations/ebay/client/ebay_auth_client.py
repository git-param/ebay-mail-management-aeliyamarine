import base64
import json
import logging
from dataclasses import dataclass
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urljoin
from urllib.request import Request, urlopen

from typing import Any

import requests

from fastapi import HTTPException, status


logger = logging.getLogger(__name__)

EBAY_OAUTH_SCOPES = [
    'https://api.ebay.com/oauth/api_scope/commerce.message',
    'https://api.ebay.com/oauth/api_scope/commerce.identity.readonly',
    'https://api.ebay.com/oauth/api_scope/sell.inventory',
    'https://api.ebay.com/oauth/api_scope/sell.fulfillment',
]
EBAY_LEGACY_REFRESH_SCOPES = [
    'https://api.ebay.com/oauth/api_scope/commerce.message',
    'https://api.ebay.com/oauth/api_scope/sell.inventory',
]
EBAY_REFRESH_SCOPES = [
    *EBAY_LEGACY_REFRESH_SCOPES,
    'https://api.ebay.com/oauth/api_scope/sell.fulfillment',
]


@dataclass(frozen=True)
class EbayTokenPayload:
    access_token: str
    refresh_token: str | None
    expires_in: int | None
    refresh_token_expires_in: int | None


@dataclass(frozen=True)
class EbaySellerIdentity:
    username: str
    user_id: str
    seller_account_id: str
    store_name: str | None


@dataclass(frozen=True)
class EbayRawApiResponse:
    status_code: int
    payload: dict | list | str
    ok: bool
    request_url: str
    request_headers: dict[str, str]

@dataclass
class EbayMediaUploadResponse:
    ok: bool
    status_code: int
    payload: Any
    headers: dict[str, str]

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

    @property
    def identity_user_url(self) -> str:
        if self.environment == 'PRODUCTION':
            return 'https://apiz.ebay.com/commerce/identity/v1/user/'
        return 'https://apiz.sandbox.ebay.com/commerce/identity/v1/user/'

    @property
    def conversations_url(self) -> str:
        if self.environment == 'PRODUCTION':
            return 'https://api.ebay.com/commerce/message/v1/conversation'
        return 'https://api.sandbox.ebay.com/commerce/message/v1/conversation'

    @property
    def fulfillment_order_url(self) -> str:
        if self.environment == 'PRODUCTION':
            return 'https://api.ebay.com/sell/fulfillment/v1/order'
        return 'https://api.sandbox.ebay.com/sell/fulfillment/v1/order'

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
        try:
            return self._refresh_access_token_with_scopes(refresh_token, EBAY_REFRESH_SCOPES)
        except HTTPException:
            # Tokens granted before order sync existed do not include sell.fulfillment.
            # Preserve message synchronization until the seller reconnects and consents.
            logger.warning('Expanded eBay token refresh failed; retrying legacy scopes')
            return self._refresh_access_token_with_scopes(refresh_token, EBAY_LEGACY_REFRESH_SCOPES)

    def _refresh_access_token_with_scopes(self, refresh_token: str, scopes: list[str]) -> EbayTokenPayload:
        return self._request_tokens(
            {
                'grant_type': 'refresh_token',
                'refresh_token': refresh_token,
                'scope': ' '.join(scopes),
            }
        )

    def get_authenticated_seller_identity(self, access_token: str) -> EbaySellerIdentity:
        request = Request(
            self.identity_user_url,
            headers={
                'Authorization': f'Bearer {access_token}',
                'Accept': 'application/json',
            },
            method='GET',
        )
        try:
            with urlopen(request, timeout=20) as response:
                data = json.loads(response.read().decode('utf-8'))
        except HTTPError as exc:
            error_body = ''
            try:
                error_body = exc.read().decode('utf-8')
            except Exception:
                pass
            logger.error(
                'eBay seller identity lookup failed. Status=%s Body=%s',
                exc.code,
                error_body,
            )
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail='Unable to verify eBay seller identity',
            ) from exc
        except (URLError, TimeoutError, json.JSONDecodeError) as exc:
            logger.warning('Unable to reach or parse eBay seller identity response')
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail='Unable to verify eBay seller identity',
            ) from exc

        username = self._non_empty_string(data.get('username'))
        user_id = self._non_empty_string(data.get('userId'))
        if not username or not user_id:
            logger.error('eBay seller identity response did not include username and userId')
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail='eBay seller identity response was invalid',
            )

        business_account = data.get('businessAccount') if isinstance(data.get('businessAccount'), dict) else {}
        store_name = (
            self._non_empty_string(business_account.get('doingBusinessAs'))
            or self._non_empty_string(business_account.get('name'))
        )
        seller_identity = EbaySellerIdentity(
            username=username,
            user_id=user_id,
            seller_account_id=user_id,
            store_name=store_name,
        )
        logger.info(
            'Verified eBay seller identity username=%s user_id=%s store_name=%s',
            seller_identity.username,
            seller_identity.user_id,
            seller_identity.store_name,
        )
        return seller_identity

    def get_conversations_raw(
        self,
        access_token: str,
        *,
        conversation_type: str = 'FROM_MEMBERS',
        limit: int = 10,
        offset: int = 0,
    ) -> EbayRawApiResponse:
        request_url = f'{self.conversations_url}?{urlencode({"conversation_type": conversation_type, "limit": limit, "offset": offset})}'
        return self._request_message_api_raw(access_token, request_url=request_url, method='GET')

    def get_conversations(
        self,
        access_token: str,
        *,
        conversation_type: str = 'FROM_MEMBERS',
        limit: int = 50,
        offset: int = 0,
    ) -> dict:
        response = self.get_conversations_raw(
            access_token,
            conversation_type=conversation_type,
            limit=limit,
            offset=offset,
        )
        if not response.ok or not isinstance(response.payload, dict):
            logger.warning('eBay conversation list request failed with status %s', response.status_code)
            raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail='eBay conversation list request failed')
        return response.payload

    def get_conversation_raw(
        self,
        access_token: str,
        *,
        conversation_id: str,
        conversation_type: str = 'FROM_MEMBERS',
        limit: int = 25,
        offset: int = 0,
    ) -> EbayRawApiResponse:
        query = urlencode({'conversation_type': conversation_type, 'limit': limit, 'offset': offset})
        request_url = f'{self.conversations_url}/{conversation_id}?{query}'
        return self._request_message_api_raw(access_token, request_url=request_url, method='GET')

    def get_conversation(
        self,
        access_token: str,
        *,
        conversation_id: str,
        conversation_type: str = 'FROM_MEMBERS',
        limit: int = 50,
        offset: int = 0,
    ) -> dict:
        response = self.get_conversation_raw(
            access_token,
            conversation_id=conversation_id,
            conversation_type=conversation_type,
            limit=limit,
            offset=offset,
        )
        if not response.ok or not isinstance(response.payload, dict):
            logger.warning(
                'eBay conversation detail request failed for %s with status %s',
                conversation_id,
                response.status_code,
            )
            raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail='eBay conversation detail request failed')
        return response.payload

    def get_order_raw(self, access_token: str, *, order_id: str) -> EbayRawApiResponse:
        request_url = f'{self.fulfillment_order_url}/{order_id}'
        return self._request_json_api_raw(access_token, request_url=request_url, method='GET')

    def get_orders_raw(
        self,
        access_token: str,
        *,
        limit: int = 200,
        offset: int = 0,
        filter_value: str | None = None,
    ) -> EbayRawApiResponse:
        query = {'limit': limit, 'offset': offset}
        if filter_value:
            query['filter'] = filter_value
        request_url = f'{self.fulfillment_order_url}?{urlencode(query)}'
        return self._request_json_api_raw(access_token, request_url=request_url, method='GET')

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

    def _non_empty_string(self, value: object) -> str | None:
        if isinstance(value, str) and value.strip():
            return value.strip()
        return None

    def _decode_response_body(self, response_body: str) -> dict | list | str:
        if not response_body:
            return {}
        try:
            return json.loads(response_body)
        except json.JSONDecodeError:
            return response_body

    def send_conversation_message(
        self,
        access_token: str,
        *,
        conversation_id: str,
        message_body: str,
        conversation_type: str = 'FROM_MEMBERS',
        message_media: list[dict] | None = None,
    ) -> EbayRawApiResponse:
        """Send a conversation reply through the eBay Message API."""
        request_url = self.conversations_url.replace('/conversation', '/send_message')
        payload = {
            'conversationId': conversation_id,
            'conversationType': conversation_type,
            'messageText': message_body,
        }
        if message_media:
            payload['messageMedia'] = message_media
        return self._request_message_api_raw(
            access_token,
            request_url=request_url,
            method='POST',
            payload=payload,
        )

    def _request_message_api_raw(
        self,
        access_token: str,
        *,
        request_url: str,
        method: str,
        payload: dict | None = None,
    ) -> EbayRawApiResponse:
        data = json.dumps(payload).encode('utf-8') if payload is not None else None
        headers = {
            'Authorization': f'Bearer {access_token}',
            'Accept': 'application/json',
        }
        if payload is not None:
            headers['Content-Type'] = 'application/json'
        request = Request(
            request_url,
            data=data,
            headers=headers,
            method=method,
        )
        sanitized_headers = self._sanitize_headers(headers)
        logger.info('Calling eBay Message API url=%s method=%s headers=%s payload=%s', request_url, method, sanitized_headers, payload)
        try:
            with urlopen(request, timeout=20) as response:
                response_body = response.read().decode('utf-8')
                logger.info(
                    'eBay Message API response url=%s method=%s status_code=%s body=%s',
                    request_url,
                    method,
                    response.status,
                    response_body,
                )
                return EbayRawApiResponse(
                    status_code=response.status,
                    payload=self._decode_response_body(response_body),
                    ok=True,
                    request_url=request_url,
                    request_headers=sanitized_headers,
                )
        except HTTPError as exc:
            error_body = ''
            try:
                error_body = exc.read().decode('utf-8')
            except Exception:
                pass
            logger.warning(
                'eBay Message API error url=%s method=%s status_code=%s body=%s',
                request_url,
                method,
                exc.code,
                error_body,
            )
            return EbayRawApiResponse(
                status_code=exc.code,
                payload=self._decode_response_body(error_body),
                ok=False,
                request_url=request_url,
                request_headers=sanitized_headers,
            )
        except (URLError, TimeoutError) as exc:
            logger.warning('Unable to reach eBay Message API endpoint url=%s method=%s', request_url, method)
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail='Unable to reach eBay Message API',
            ) from exc

    def _request_json_api_raw(
        self,
        access_token: str,
        *,
        request_url: str,
        method: str,
        payload: dict | None = None,
    ) -> EbayRawApiResponse:
        data = json.dumps(payload).encode('utf-8') if payload is not None else None
        headers = {
            'Authorization': f'Bearer {access_token}',
            'Accept': 'application/json',
        }
        if payload is not None:
            headers['Content-Type'] = 'application/json'
        request = Request(request_url, data=data, headers=headers, method=method)
        sanitized_headers = self._sanitize_headers(headers)
        logger.info('Calling eBay JSON API url=%s method=%s headers=%s', request_url, method, sanitized_headers)
        try:
            with urlopen(request, timeout=20) as response:
                response_body = response.read().decode('utf-8')
                return EbayRawApiResponse(
                    status_code=response.status,
                    payload=self._decode_response_body(response_body),
                    ok=True,
                    request_url=request_url,
                    request_headers=sanitized_headers,
                )
        except HTTPError as exc:
            error_body = ''
            try:
                error_body = exc.read().decode('utf-8')
            except Exception:
                pass
            logger.warning(
                'eBay JSON API error url=%s method=%s status_code=%s body=%s',
                request_url,
                method,
                exc.code,
                error_body,
            )
            return EbayRawApiResponse(
                status_code=exc.code,
                payload=self._decode_response_body(error_body),
                ok=False,
                request_url=request_url,
                request_headers=sanitized_headers,
            )
        except (URLError, TimeoutError) as exc:
            logger.warning('Unable to reach eBay JSON API endpoint url=%s method=%s', request_url, method)
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail='Unable to reach eBay API',
            ) from exc
    def upload_message_media(
        self,
        access_token: str,
        *,
        file_bytes: bytes,
        mime_type: str,
        media_name: str,
    ) -> EbayMediaUploadResponse:
        """
        Upload an image to eBay Media API and return mediaUrl for MessageMedia.
        """

        media_base_url = getattr(
            self,
            "media_base_url",
            "https://apim.ebay.com/commerce/media/v1_beta",
        )

        create_url = f"{media_base_url.rstrip('/')}/image/create_image_from_file"

        headers = {
            "Authorization": f"Bearer {access_token}",
            "Accept": "application/json",
        }

        files = {
            "image": (
                media_name,
                file_bytes,
                mime_type,
            )
        }

        try:
            create_response = requests.post(
                create_url,
                headers=headers,
                files=files,
                timeout=60,
            )

            try:
                create_payload = create_response.json()
            except ValueError:
                create_payload = {"raw": create_response.text}

            if not create_response.ok:
                return EbayMediaUploadResponse(
                    ok=False,
                    status_code=create_response.status_code,
                    payload=create_payload,
                    headers=dict(create_response.headers),
                )

            # eBay createImageFromFile can return the image resource in Location header.
            location = create_response.headers.get("Location")

            final_payload = create_payload if isinstance(create_payload, dict) else {}

            # Sometimes imageUrl may already be present.
            image_url = (
                final_payload.get("imageUrl")
                or final_payload.get("maxDimensionImageUrl")
                or final_payload.get("mediaUrl")
            )

            # If imageUrl is not directly returned, call getImage using Location.
            if not image_url and location:
                get_url = location if location.startswith("http") else urljoin(media_base_url.rstrip("/") + "/", location.lstrip("/"))

                get_response = requests.get(
                    get_url,
                    headers=headers,
                    timeout=60,
                )

                try:
                    get_payload = get_response.json()
                except ValueError:
                    get_payload = {"raw": get_response.text}

                if not get_response.ok:
                    return EbayMediaUploadResponse(
                        ok=False,
                        status_code=get_response.status_code,
                        payload=get_payload,
                        headers=dict(get_response.headers),
                    )

                if isinstance(get_payload, dict):
                    final_payload.update(get_payload)
                    image_url = (
                        get_payload.get("imageUrl")
                        or get_payload.get("maxDimensionImageUrl")
                        or get_payload.get("mediaUrl")
                    )

            if image_url:
                final_payload["mediaUrl"] = image_url

            if location:
                final_payload["location"] = location

            return EbayMediaUploadResponse(
                ok=True,
                status_code=create_response.status_code,
                payload=final_payload,
                headers=dict(create_response.headers),
            )

        except requests.RequestException as exc:
            return EbayMediaUploadResponse(
                ok=False,
                status_code=0,
                payload={
                    "errors": [
                        {
                            "message": str(exc),
                            "longMessage": f"eBay media upload request failed: {exc}",
                        }
                    ]
                },
                headers={},
            )

    def _sanitize_headers(self, headers: dict[str, str]) -> dict[str, str]:
        sanitized_headers = dict(headers)
        if 'Authorization' in sanitized_headers:
            scheme = sanitized_headers['Authorization'].split(' ', 1)[0]
            sanitized_headers['Authorization'] = f'{scheme} ***'
        return sanitized_headers
