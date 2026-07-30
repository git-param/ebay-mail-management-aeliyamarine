import base64
import json
import logging
import xml.etree.ElementTree as ET
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
# eBay does not publish a separate ``sell.negotiation`` OAuth scope. The
# Negotiation API is authorized by sell.inventory (included above).
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
    response_headers: dict[str, str] | None = None

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
        media_base_url: str = '',
    ):
        self.client_id = client_id
        self.client_secret = client_secret
        self.redirect_uri = redirect_uri
        self.runame = runame
        self.environment = environment.upper()
        self.media_base_url = media_base_url.rstrip('/') if media_base_url else ''
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
    def default_media_base_url(self) -> str:
        if self.environment == 'PRODUCTION':
            return 'https://apim.ebay.com/commerce/media/v1_beta'
        return 'https://apim.sandbox.ebay.com/commerce/media/v1_beta'

    @property
    def fulfillment_order_url(self) -> str:
        if self.environment == 'PRODUCTION':
            return 'https://api.ebay.com/sell/fulfillment/v1/order'
        return 'https://api.sandbox.ebay.com/sell/fulfillment/v1/order'

    @property
    def negotiation_url(self) -> str:
        host = 'https://api.ebay.com' if self.environment == 'PRODUCTION' else 'https://api.sandbox.ebay.com'
        return f'{host}/sell/negotiation/v1'

    @property
    def trading_url(self) -> str:
        return 'https://api.ebay.com/ws/api.dll' if self.environment == 'PRODUCTION' else 'https://api.sandbox.ebay.com/ws/api.dll'

    def get_best_offers_raw(
        self,
        access_token: str,
        *,
        page: int = 1,
        entries_per_page: int = 200,
        best_offer_status: str = 'All',
        item_id: str | None = None,
    ) -> EbayRawApiResponse:
        """Retrieve Best Offers through eBay's official Trading API."""
        item_filter = f'<ItemID>{item_id}</ItemID>' if item_id else ''
        body = (
            '<?xml version="1.0" encoding="utf-8"?>'
            '<GetBestOffersRequest xmlns="urn:ebay:apis:eBLBaseComponents">'
            f'<DetailLevel>ReturnAll</DetailLevel>{item_filter}<BestOfferStatus>{best_offer_status}</BestOfferStatus>'
            f'<Pagination><EntriesPerPage>{entries_per_page}</EntriesPerPage><PageNumber>{page}</PageNumber></Pagination>'
            '</GetBestOffersRequest>'
        ).encode('utf-8')
        headers = {
            'X-EBAY-API-CALL-NAME': 'GetBestOffers', 'X-EBAY-API-SITEID': '0',
            'X-EBAY-API-COMPATIBILITY-LEVEL': '1455', 'X-EBAY-API-IAF-TOKEN': access_token,
            'Content-Type': 'text/xml',
        }
        request = Request(self.trading_url, data=body, headers=headers, method='POST')
        safe_headers = self._sanitize_headers(headers)
        try:
            with urlopen(request, timeout=30) as response:
                xml = response.read().decode('utf-8')
                payload = self._best_offers_xml(xml)
                return EbayRawApiResponse(
                    response.status,
                    payload,
                    payload.get('ack') in {'Success', 'Warning'},
                    self.trading_url,
                    safe_headers,
                    dict(response.headers.items()),
                )
        except HTTPError as exc:
            xml = exc.read().decode('utf-8', errors='replace')
            return EbayRawApiResponse(
                exc.code,
                self._best_offers_xml(xml),
                False,
                self.trading_url,
                safe_headers,
                dict(exc.headers.items()) if exc.headers else None,
            )
        except (URLError, TimeoutError, ET.ParseError) as exc:
            raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail='Unable to retrieve eBay buyer offers') from exc

    def _best_offers_xml(self, xml: str) -> dict:
        root = ET.fromstring(xml)
        ns = {'e': 'urn:ebay:apis:eBLBaseComponents'}
        error = root.find('.//e:Errors/e:LongMessage', ns)
        ack = root.findtext('./e:Ack', default='', namespaces=ns)
        offers = []
        grouped = root.findall('.//e:ItemBestOffers', ns)
        if grouped:
            for group in grouped:
                item_id = group.findtext('./e:Item/e:ItemID', namespaces=ns)
                for node in group.findall('./e:BestOfferArray/e:BestOffer', ns):
                    offers.append(self._best_offer_node(node, item_id, ns))
        else:
            item_id = root.findtext('./e:Item/e:ItemID', namespaces=ns)
            for node in root.findall('./e:BestOfferArray/e:BestOffer', ns):
                offers.append(self._best_offer_node(node, item_id, ns))
        pages = root.findtext('.//e:PaginationResult/e:TotalNumberOfPages', default='1', namespaces=ns)
        return {'offers': offers, 'totalPages': int(pages or 1), 'error': error.text if error is not None else None, 'ack': ack}

    def _best_offer_node(self, node, item_id, ns) -> dict:
        price = node.find('./e:Price', ns)
        return {
            'offerId': node.findtext('./e:BestOfferID', namespaces=ns),
            'listingId': item_id,
            'buyerUsername': node.findtext('./e:Buyer/e:UserID', namespaces=ns),
            'buyerMessage': node.findtext('./e:BuyerMessage', namespaces=ns),
            'sellerMessage': node.findtext('./e:SellerMessage', namespaces=ns),
            'expirationTime': node.findtext('./e:ExpirationTime', namespaces=ns),
            'amount': price.text if price is not None else None,
            'currency': price.get('currencyID') if price is not None else None,
            'quantity': node.findtext('./e:Quantity', default='1', namespaces=ns),
            'status': node.findtext('./e:Status', default='Pending', namespaces=ns),
            'offerType': node.findtext('./e:BestOfferCodeType', namespaces=ns),
            'createdTime': (
                node.findtext('./e:CreatedTime', namespaces=ns)
                or node.findtext('./e:CreationTime', namespaces=ns)
                or node.findtext('./e:BestOfferCreatedTime', namespaces=ns)
                or node.findtext('./e:OfferTime', namespaces=ns)
                or node.findtext('./e:StartTime', namespaces=ns)
            ),
        }

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
        logger.warning(
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

        logger.warning('eBay OAuth token request succeeded')

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
            'messageText': self._message_body_for_send(message_body, has_media=bool(message_media)),
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
        logger.warning('Calling eBay Message API url=%s method=%s headers=%s payload=%s', request_url, method, sanitized_headers, payload)
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

    def _message_body_for_send(self, message_body: str, *, has_media: bool) -> str:
        """
        Preserve paragraph spacing when eBay renders messages with media.

        eBay can collapse fully empty lines in attachment replies. A single
        space on otherwise blank lines keeps the intended paragraph breaks
        without changing visible text.
        """
        if not has_media:
            return message_body

        normalized = message_body.replace('\r\n', '\n').replace('\r', '\n')
        return '\n'.join(line if line else ' ' for line in normalized.split('\n'))

    def _request_json_api_raw(
        self,
        access_token: str,
        *,
        request_url: str,
        method: str,
        payload: dict | None = None,
        extra_headers: dict[str, str] | None = None,
    ) -> EbayRawApiResponse:
        data = json.dumps(payload).encode('utf-8') if payload is not None else None
        headers = {
            'Authorization': f'Bearer {access_token}',
            'Accept': 'application/json',
        }
        if extra_headers:
            headers.update(extra_headers)
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

        media_base_url = self.media_base_url or self.default_media_base_url

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
                    "error_type": "transport_error",
                    "errors": [
                        {
                            "message": str(exc),
                            "longMessage": f"Could not connect to eBay media upload service: {exc}",
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


    # deepseek code suggesstions
    def get_my_messages_raw(
        self,
        access_token: str,
        *,
        page_number: int = 1,
        entries_per_page: int = 100,
        detail_level: str = "ReturnHeaders",
        message_ids: list[str] | None = None,
    ) -> EbayRawApiResponse:
        """Fetch My Messages inbox via eBay Trading API."""
        
        xml_parts = [
            '<?xml version="1.0" encoding="utf-8"?>',
            '<GetMyMessagesRequest xmlns="urn:ebay:apis:eBLBaseComponents">',
            f'<DetailLevel>{detail_level}</DetailLevel>',
        ]
        
        # Add MessageIDs if provided
        if message_ids:
            xml_parts.append('<MessageIDs>')
            for msg_id in message_ids:
                xml_parts.append(f'<MessageID>{msg_id}</MessageID>')
            xml_parts.append('</MessageIDs>')
        else:
            xml_parts.extend([
                '<Pagination>',
                f'    <EntriesPerPage>{entries_per_page}</EntriesPerPage>',
                f'    <PageNumber>{page_number}</PageNumber>',
                '</Pagination>',
            ])
        
        xml_parts.append('</GetMyMessagesRequest>')
        body = ''.join(xml_parts).encode('utf-8')
        
        headers = {
            'X-EBAY-API-CALL-NAME': 'GetMyMessages',
            'X-EBAY-API-SITEID': '0',
            'X-EBAY-API-COMPATIBILITY-LEVEL': '1455',
            'X-EBAY-API-IAF-TOKEN': access_token,
            'Content-Type': 'text/xml',
        }
        
        request = Request(self.trading_url, data=body, headers=headers, method='POST')
        safe_headers = self._sanitize_headers(headers)
        
        try:
            with urlopen(request, timeout=30) as response:
                xml_response = response.read().decode('utf-8')
                payload = self._my_messages_xml(xml_response)
                return EbayRawApiResponse(
                    response.status,
                    payload,
                    payload.get('ack') in {'Success', 'Warning'},
                    self.trading_url,
                    safe_headers
                )
        except HTTPError as exc:
            xml_response = exc.read().decode('utf-8', errors='replace')
            return EbayRawApiResponse(
                exc.code,
                self._my_messages_xml(xml_response),
                False,
                self.trading_url,
                safe_headers
            )
        except (URLError, TimeoutError) as exc:
            logger.error(f"GetMyMessages network error: {exc}")
            return EbayRawApiResponse(
                500,
                {'error': str(exc)},
                False,
                self.trading_url,
                safe_headers
            )

    def _my_messages_xml(self, xml: str) -> dict:
        """Parse GetMyMessages XML response."""
        try:
            root = ET.fromstring(xml)
        except ET.ParseError:
            return {'messages': [], 'error': 'Invalid XML', 'ack': 'Failure'}
        
        ns = {'e': 'urn:ebay:apis:eBLBaseComponents'}
        
        ack = root.findtext('./e:Ack', default='', namespaces=ns)
        error = root.find('.//e:Errors/e:LongMessage', ns)
        
        messages = []
        
        # Try different paths for messages
        for path in ['.//e:Message', './/e:Messages/e:Message']:
            for node in root.findall(path, ns):
                msg = {
                    'message_id': node.findtext('./e:MessageID', namespaces=ns),
                    'subject': node.findtext('./e:Subject', namespaces=ns),
                    'body': node.findtext('./e:Body', namespaces=ns),
                    'sender': node.findtext('./e:Sender', namespaces=ns),
                    'recipient': node.findtext('./e:RecipientUserID', namespaces=ns),
                    'message_type': node.findtext('./e:MessageType', namespaces=ns),
                    'sent_date': node.findtext('./e:SentDate', namespaces=ns),
                    'receive_date': node.findtext('./e:ReceiveDate', namespaces=ns),
                    'item_id': node.findtext('./e:ItemID', namespaces=ns),
                    'message_status': node.findtext('./e:MessageStatus', namespaces=ns),
                    'read': node.findtext('./e:Read', namespaces=ns) == 'true',
                    'flagged': node.findtext('./e:Flagged', namespaces=ns) == 'true',
                }
                messages.append(msg)
        
        total_pages = root.findtext(
            './/e:PaginationResult/e:TotalNumberOfPages',
            default='1',
            namespaces=ns
        )
        
        return {
            'messages': messages,
            'total_pages': int(total_pages or 1),
            'error': error.text if error is not None else None,
            'ack': ack
        }

    def get_message_details_raw(
        self,
        access_token: str,
        *,
        message_ids: list[str],
    ) -> EbayRawApiResponse:
        """Fetch full details for specific messages."""
        # Build XML request with MessageID list
        xml_parts = [
            '<?xml version="1.0" encoding="utf-8"?>',
            '<GetMyMessagesRequest xmlns="urn:ebay:apis:eBLBaseComponents">',
            '<DetailLevel>ReturnMessages</DetailLevel>',
        ]
        
        for msg_id in message_ids:
            xml_parts.append(f'<MessageID>{msg_id}</MessageID>')
        
        xml_parts.append('</GetMyMessagesRequest>')
        body = ''.join(xml_parts).encode('utf-8')
        
        headers = {
            'X-EBAY-API-CALL-NAME': 'GetMyMessages',
            'X-EBAY-API-SITEID': '0',
            'X-EBAY-API-COMPATIBILITY-LEVEL': '1455',
            'X-EBAY-API-IAF-TOKEN': access_token,
            'Content-Type': 'text/xml',
        }
        
        request = Request(self.trading_url, data=body, headers=headers, method='POST')
        safe_headers = self._sanitize_headers(headers)
        
        try:
            with urlopen(request, timeout=30) as response:
                xml = response.read().decode('utf-8')
                payload = self._my_messages_xml(xml)
                return EbayRawApiResponse(
                    response.status,
                    payload,
                    payload.get('ack') in {'Success', 'Warning'},
                    self.trading_url,
                    safe_headers
                )
        except HTTPError as exc:
            xml = exc.read().decode('utf-8', errors='replace')
            return EbayRawApiResponse(
                exc.code,
                self._my_messages_xml(xml),
                False,
                self.trading_url,
                safe_headers
            )
        except (URLError, TimeoutError, ET.ParseError) as exc:
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail='Unable to retrieve eBay message details'
            ) from exc

    # In app/modules/integrations/ebay/client/ebay_auth_client.py

    def get_offer_details_raw(self, access_token: str, offer_id: str) -> dict:
        """
        Fetch detailed information about a specific offer.
        """
        request_url = f"https://api.ebay.com/sell/negotiation/v1/offer/{offer_id}"
        return self._request_raw(
            access_token=access_token,
            request_url=request_url,
            method='GET',
            api_type='sell'
        )

    def get_my_messages_debug(
        self,
        access_token: str,
        detail_level: str = "ReturnHeaders",
        message_type: str | None = None,
    ) -> EbayRawApiResponse:
        """Debug method to test GetMyMessages with different detail levels."""
        
        xml_parts = [
            '<?xml version="1.0" encoding="utf-8"?>',
            '<GetMyMessagesRequest xmlns="urn:ebay:apis:eBLBaseComponents">',
            f'<DetailLevel>{detail_level}</DetailLevel>',
        ]
        
        if message_type:
            xml_parts.append(f'<MessageType>{message_type}</MessageType>')
        
        xml_parts.extend([
            '<Pagination>',
            '    <EntriesPerPage>20</EntriesPerPage>',
            '    <PageNumber>1</PageNumber>',
            '</Pagination>',
            '</GetMyMessagesRequest>'
        ])
        
        xml_body = ''.join(xml_parts).encode('utf-8')
        
        headers = {
            'X-EBAY-API-CALL-NAME': 'GetMyMessages',
            'X-EBAY-API-SITEID': '0',
            'X-EBAY-API-COMPATIBILITY-LEVEL': '1455',
            'X-EBAY-API-IAF-TOKEN': access_token,
            'Content-Type': 'text/xml',
        }
        
        request = Request(self.trading_url, data=xml_body, headers=headers, method='POST')
        safe_headers = self._sanitize_headers(headers)
        
        logger.warning(f"GetMyMessages Debug: detail_level={detail_level}, message_type={message_type}")
        
        try:
            with urlopen(request, timeout=30) as response:
                xml_response = response.read().decode('utf-8')
                logger.warning(f"GetMyMessages Debug Response: {xml_response[:500]}...")
                return EbayRawApiResponse(
                    response.status,
                    self._my_messages_xml(xml_response),
                    True,
                    self.trading_url,
                    safe_headers
                )
        except HTTPError as exc:
            xml_response = exc.read().decode('utf-8', errors='replace')
            logger.error(f"GetMyMessages Debug Error: {xml_response[:500]}...")
            return EbayRawApiResponse(
                exc.code,
                self._my_messages_xml(xml_response),
                False,
                self.trading_url,
                safe_headers
            )
        except (URLError, TimeoutError) as exc:
            logger.error(f"GetMyMessages Debug Network Error: {exc}")
            return EbayRawApiResponse(
                500,
                {'error': str(exc)},
                False,
                self.trading_url,
                safe_headers
            )
