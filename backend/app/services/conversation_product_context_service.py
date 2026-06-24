import base64
import json
import logging
from datetime import UTC, datetime, timedelta
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from uuid import UUID

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models.conversation import Conversation
from app.models.order_context import ConversationProductContext, EbayOrderLineItem


logger = logging.getLogger(__name__)


class ConversationProductContextService:
    def __init__(self, db: Session):
        self.db = db
        self.settings = get_settings()
        self._app_token: str | None = None
        self._app_token_expires_at: datetime | None = None

    def context_for_conversation(self, conversation: Conversation) -> ConversationProductContext | None:
        context = self.get_context(conversation.id)
        if context:
            return context
        return self.enrich_conversation(conversation)

    def get_context(self, conversation_id: UUID) -> ConversationProductContext | None:
        return self.db.scalar(
            select(ConversationProductContext).where(ConversationProductContext.conversation_id == conversation_id)
        )

    def enrich_conversation(self, conversation: Conversation) -> ConversationProductContext | None:
        if conversation.id is None:
            self.db.flush()

        reference_id = self._string(conversation.reference_id)
        reference_type = self._string(conversation.reference_type)
        logger.info(
            'Product context enrichment started conversation_id=%s reference_id=%s reference_type=%s',
            conversation.id,
            reference_id or 'not found',
            reference_type or 'not found',
        )
        if reference_type != 'LISTING' or not reference_id:
            return None

        context = self.get_context(conversation.id)
        if not context:
            context = ConversationProductContext(
                conversation_id=conversation.id,
                reference_id=reference_id,
                reference_type=reference_type,
                item_url=self._item_url(reference_id),
                enrichment_status='PENDING',
            )
            self.db.add(context)
        else:
            context.reference_id = reference_id
            context.reference_type = reference_type
            context.item_url = self._item_url(reference_id)

        browse_payload = None
        try:
            browse_payload = self._get_item_by_legacy_id(reference_id)
            context.item_title = self._string(browse_payload.get('title'))
            image = browse_payload.get('image') if isinstance(browse_payload.get('image'), dict) else {}
            seller = browse_payload.get('seller') if isinstance(browse_payload.get('seller'), dict) else {}
            context.image_url = self._string(image.get('imageUrl'))
            context.seller_username = self._string(seller.get('username'))
            context.raw_payload = browse_payload
            context.enrichment_status = 'ENRICHED'
            logger.info(
                'Browse API success conversation_id=%s reference_id=%s title_fetched=%s image_fetched=%s seller_fetched=%s',
                conversation.id,
                reference_id,
                bool(context.item_title),
                bool(context.image_url),
                bool(context.seller_username),
            )
        except Exception as exc:
            context.enrichment_status = 'FAILED'
            context.raw_payload = {'error': str(exc)}
            logger.warning(
                'Browse API failure conversation_id=%s reference_id=%s error=%s',
                conversation.id,
                reference_id,
                exc,
            )

        self._match_local_sku_and_order(context)
        context.last_enriched_at = datetime.now(UTC)
        return context

    def serialize(self, context: ConversationProductContext | None) -> dict | None:
        if not context:
            return None
        return {
            'reference_id': context.reference_id,
            'title': context.item_title or '',
            'image_url': context.image_url or '',
            'seller_username': context.seller_username or '',
            'item_url': context.item_url or self._item_url(context.reference_id),
            'sku': context.sku,
            'order_id': context.order_id,
            'enrichment_status': context.enrichment_status,
        }

    def _match_local_sku_and_order(self, context: ConversationProductContext) -> None:
        line_item = self.db.scalar(
            select(EbayOrderLineItem)
            .where(or_(EbayOrderLineItem.item_id == context.reference_id, EbayOrderLineItem.listing_id == context.reference_id))
            .order_by(EbayOrderLineItem.updated_at.desc(), EbayOrderLineItem.created_at.desc())
            .limit(1)
        )
        if line_item:
            context.sku = line_item.sku
            context.order_id = line_item.order_id
        logger.info(
            'Product context local match conversation_id=%s reference_id=%s sku_matched=%s order_matched=%s',
            context.conversation_id,
            context.reference_id,
            bool(context.sku),
            bool(context.order_id),
        )

    def _get_item_by_legacy_id(self, reference_id: str) -> dict:
        token = self._get_app_token()
        base_url = 'https://api.ebay.com/buy/browse/v1/item/get_item_by_legacy_id'
        if self.settings.ebay_environment.upper() != 'PRODUCTION':
            base_url = 'https://api.sandbox.ebay.com/buy/browse/v1/item/get_item_by_legacy_id'
        request_url = f'{base_url}?{urlencode({"legacy_item_id": reference_id})}'
        request = Request(
            request_url,
            headers={
                'Authorization': f'Bearer {token}',
                'Accept': 'application/json',
                'X-EBAY-C-MARKETPLACE-ID': 'EBAY_US',
            },
            method='GET',
        )
        try:
            with urlopen(request, timeout=30) as response:
                payload = json.loads(response.read().decode('utf-8') or '{}')
        except HTTPError as exc:
            body = exc.read().decode('utf-8')
            raise RuntimeError(f'Browse API returned {exc.code}: {body}') from exc
        except (URLError, TimeoutError, json.JSONDecodeError) as exc:
            raise RuntimeError(f'Browse API request failed: {exc}') from exc
        if not isinstance(payload, dict):
            raise RuntimeError('Browse API returned non-object payload')
        return payload

    def _get_app_token(self) -> str:
        now = datetime.now(UTC)
        if self._app_token and self._app_token_expires_at and self._app_token_expires_at > now + timedelta(minutes=2):
            return self._app_token

        token_url = 'https://api.ebay.com/identity/v1/oauth2/token'
        if self.settings.ebay_environment.upper() != 'PRODUCTION':
            token_url = 'https://api.sandbox.ebay.com/identity/v1/oauth2/token'
        body = urlencode(
            {
                'grant_type': 'client_credentials',
                'scope': 'https://api.ebay.com/oauth/api_scope',
            }
        ).encode('utf-8')
        credentials = base64.b64encode(
            f'{self.settings.ebay_client_id}:{self.settings.ebay_client_secret}'.encode('utf-8')
        ).decode('ascii')
        request = Request(
            token_url,
            data=body,
            headers={
                'Authorization': f'Basic {credentials}',
                'Content-Type': 'application/x-www-form-urlencoded',
                'Accept': 'application/json',
            },
            method='POST',
        )
        with urlopen(request, timeout=30) as response:
            payload = json.loads(response.read().decode('utf-8') or '{}')
        self._app_token = payload['access_token']
        self._app_token_expires_at = now + timedelta(seconds=int(payload.get('expires_in') or 7200))
        return self._app_token

    def _item_url(self, reference_id: str) -> str:
        return f'https://www.ebay.com/itm/{reference_id}'

    def _string(self, value: object) -> str | None:
        return value.strip() if isinstance(value, str) and value.strip() else None
