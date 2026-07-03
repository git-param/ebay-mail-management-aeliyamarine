import base64
import json
import logging
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from time import sleep
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from uuid import UUID

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models.conversation import Conversation
from app.models.ebay_account import EbayAccount
from app.models.order_context import ConversationOrderContext, ConversationProductContext, EbayOrder, EbayOrderLineItem


logger = logging.getLogger(__name__)

TERMINAL_BROWSE_ERROR_IDS = {11001, 11003}
TERMINAL_ENRICHMENT_STATUSES = {'UNAVAILABLE', 'ENRICHED', 'LOCAL_ORDER'}


@dataclass(frozen=True)
class BrowseApiError(RuntimeError):
    status_code: int | None
    error_id: int | None
    message: str
    payload: object | None = None
    transient: bool = False

    def __str__(self) -> str:
        prefix = f'Browse API returned {self.status_code}' if self.status_code else 'Browse API request failed'
        return f'{prefix}: {self.message}'


class ConversationProductContextService:
    def __init__(self, db: Session):
        self.db = db
        self.settings = get_settings()
        self._app_token: str | None = None
        self._app_token_expires_at: datetime | None = None
        self._app_token_environment: str | None = None
        self._reference_cache: dict[tuple[str, str, str], ConversationProductContext] = {}

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
        same_reference = bool(context and context.reference_id == reference_id)
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

        # Backfill normalized commerce fields from the already-cached payload without another API call.
        if isinstance(context.raw_payload, dict) and context.enrichment_status == 'ENRICHED':
            price = context.raw_payload.get('price') if isinstance(context.raw_payload.get('price'), dict) else {}
            context.price_value = context.price_value or self._decimal_or_none(price.get('value'))
            context.price_currency = context.price_currency or self._string(price.get('currency'))
            options = {str(option).upper() for option in (context.raw_payload.get('buyingOptions') or []) if option}
            # BEST_OFFER means buyers may make offers on the listing. It does
            # not mean the seller may send an offer; Negotiation API eligibility
            # synchronization owns offer_available.
            context.buy_now_available = context.buy_now_available or bool({'FIXED_PRICE', 'BUY_IT_NOW'} & options)
            context.cta_type = context.cta_type or ('BUY_IT_NOW' if context.buy_now_available else None)

        cache_key = self._cache_key(conversation, reference_id)
        orders_changed = self._orders_changed_since(context, conversation)
        needs_local_upgrade = (
            context.enrichment_status == 'ENRICHED'
            and (not context.sku or not context.order_id)
            and orders_changed
        )
        if same_reference and context.enrichment_status == 'LOCAL_ORDER':
            logger.debug(
                'Skipping cached product enrichment conversation_id=%s reference_id=%s status=%s',
                conversation.id,
                reference_id,
                context.enrichment_status,
            )
            return context
        if same_reference and context.enrichment_status == 'ENRICHED' and not needs_local_upgrade:
            logger.debug(
                'Skipping cached product enrichment conversation_id=%s reference_id=%s status=%s',
                conversation.id,
                reference_id,
                context.enrichment_status,
            )
            return context

        should_check_local = context.enrichment_status != 'UNAVAILABLE' or orders_changed
        if should_check_local and self._enrich_from_local_order(conversation, context):
            context.enrichment_status = 'LOCAL_ORDER'
            context.last_enriched_at = datetime.now(UTC)
            self._reference_cache[cache_key] = context
            return context

        if same_reference and context.enrichment_status in {'UNAVAILABLE', 'ENRICHED'}:
            logger.debug(
                'Skipping cached product enrichment conversation_id=%s reference_id=%s status=%s',
                conversation.id,
                reference_id,
                context.enrichment_status,
            )
            return context

        cached = self._reference_cache.get(cache_key) or self._find_cached_context(conversation, reference_id)
        if cached and cached.id != context.id:
            self._copy_cached_context(cached, context)
            logger.debug(
                'Reused cached product enrichment conversation_id=%s reference_id=%s status=%s',
                conversation.id,
                reference_id,
                context.enrichment_status,
            )
            return context

        try:
            browse_payload = self._get_item_by_legacy_id(reference_id, environment=self._environment(conversation))
            context.item_title = self._string(browse_payload.get('title'))
            image = browse_payload.get('image') if isinstance(browse_payload.get('image'), dict) else {}
            seller = browse_payload.get('seller') if isinstance(browse_payload.get('seller'), dict) else {}
            context.image_url = self._string(image.get('imageUrl'))
            context.seller_username = self._string(seller.get('username'))
            price = browse_payload.get('price') if isinstance(browse_payload.get('price'), dict) else {}
            context.price_value = self._decimal_or_none(price.get('value'))
            context.price_currency = self._string(price.get('currency'))
            buying_options = {
                str(option).upper() for option in (browse_payload.get('buyingOptions') or []) if option
            }
            context.offer_available = False
            context.buy_now_available = 'FIXED_PRICE' in buying_options or 'BUY_IT_NOW' in buying_options
            context.cta_type = 'BUY_IT_NOW' if context.buy_now_available else None
            context.raw_payload = browse_payload
            context.enrichment_status = 'ENRICHED'
            context.last_enriched_at = datetime.now(UTC)
            self._reference_cache[cache_key] = context
            logger.info(
                'Browse API success conversation_id=%s reference_id=%s title_fetched=%s image_fetched=%s seller_fetched=%s',
                conversation.id,
                reference_id,
                bool(context.item_title),
                bool(context.image_url),
                bool(context.seller_username),
            )
        except BrowseApiError as exc:
            terminal = exc.status_code == 404 and exc.error_id in TERMINAL_BROWSE_ERROR_IDS
            context.enrichment_status = 'UNAVAILABLE' if terminal else 'FAILED'
            context.raw_payload = {
                'error': {
                    'status_code': exc.status_code,
                    'error_id': exc.error_id,
                    'message': exc.message,
                    'transient': exc.transient,
                    'response': exc.payload,
                }
            }
            if terminal:
                self._reference_cache[cache_key] = context
                logger.info(
                    'eBay listing unavailable; terminal result cached conversation_id=%s reference_id=%s error_id=%s',
                    conversation.id,
                    reference_id,
                    exc.error_id,
                )
            else:
                self._reference_cache[cache_key] = context
                logger.warning(
                    'Browse API failure conversation_id=%s reference_id=%s error=%s',
                    conversation.id,
                    reference_id,
                    exc,
                )
        except Exception as exc:
            context.enrichment_status = 'FAILED'
            context.raw_payload = {'error': {'message': str(exc), 'transient': False}}
            self._reference_cache[cache_key] = context
            logger.exception(
                'Unexpected Browse enrichment failure conversation_id=%s reference_id=%s',
                conversation.id,
                reference_id,
            )

        context.last_enriched_at = datetime.now(UTC)
        return context

    def serialize(self, context: ConversationProductContext | None) -> dict | None:
        if not context:
            return None
        raw = context.raw_payload if isinstance(context.raw_payload, dict) else {}
        raw_price = raw.get('price') if isinstance(raw.get('price'), dict) else {}
        options = {str(option).upper() for option in (raw.get('buyingOptions') or []) if option}
        offer_available = bool(context.offer_available or 'BEST_OFFER' in options)
        buy_now_available = bool(context.buy_now_available or {'FIXED_PRICE', 'BUY_IT_NOW'} & options)
        return {
            'reference_id': context.reference_id,
            'title': context.item_title or '',
            'image_url': context.image_url or '',
            'seller_username': context.seller_username or '',
            'item_url': context.item_url or self._item_url(context.reference_id),
            'price': float(context.price_value) if context.price_value is not None else self._decimal_or_none(raw_price.get('value')),
            'currency': context.price_currency or self._string(raw_price.get('currency')) or '',
            'offer_available': offer_available,
            'buy_now_available': buy_now_available,
            'cta_type': context.cta_type or ('SEND_OFFER' if offer_available else ('BUY_IT_NOW' if buy_now_available else '')),
            'sku': context.sku,
            'order_id': context.order_id,
            'enrichment_status': context.enrichment_status,
        }

    @staticmethod
    def _decimal_or_none(value: object) -> float | None:
        """Convert an eBay monetary value to a storable number without failing enrichment."""
        try:
            return float(value) if value not in (None, '') else None
        except (TypeError, ValueError):
            return None

    def _enrich_from_local_order(self, conversation: Conversation, context: ConversationProductContext) -> bool:
        if not conversation.provider_account_id:
            return False
        mapping = self.db.scalar(
            select(ConversationOrderContext).where(ConversationOrderContext.conversation_id == conversation.id)
        )
        candidate_sku = self._string(mapping.sku) if mapping else None
        identifiers = [
            EbayOrderLineItem.item_id == context.reference_id,
            EbayOrderLineItem.listing_id == context.reference_id,
        ]
        if candidate_sku:
            identifiers.append(EbayOrderLineItem.sku == candidate_sku)
        statement = (
            select(EbayOrderLineItem)
            .join(EbayOrder, EbayOrder.id == EbayOrderLineItem.order_record_id)
            .where(EbayOrderLineItem.account_id == conversation.provider_account_id)
            .where(or_(*identifiers))
        )
        if conversation.buyer_identifier:
            statement = statement.where(func.lower(EbayOrder.buyer_username) == conversation.buyer_identifier.casefold())
        line_item = self.db.scalar(
            statement.order_by(
                EbayOrder.external_created_at.desc().nullslast(),
                EbayOrder.order_id.asc(),
                EbayOrderLineItem.line_item_id.asc(),
            ).limit(1)
        )
        if not line_item and conversation.buyer_identifier:
            line_item = self.db.scalar(
                select(EbayOrderLineItem)
                .join(EbayOrder, EbayOrder.id == EbayOrderLineItem.order_record_id)
                .where(EbayOrderLineItem.account_id == conversation.provider_account_id)
                .where(or_(*identifiers))
                .order_by(EbayOrder.external_created_at.desc().nullslast(), EbayOrder.order_id.asc())
                .limit(1)
            )
        if line_item:
            context.sku = line_item.sku or context.sku
            context.order_id = line_item.order_id
            context.item_title = line_item.title or context.item_title
            context.image_url = line_item.image_url or context.image_url
            context.price_value = line_item.price_value or context.price_value
            context.price_currency = line_item.price_currency or context.price_currency
            context.raw_payload = {'source': 'LOCAL_ORDER_LINE_ITEM', 'line_item': line_item.raw_payload}
        logger.info(
            'Product context local match conversation_id=%s reference_id=%s matched=%s',
            context.conversation_id,
            context.reference_id,
            bool(line_item),
        )
        return line_item is not None

    def _get_item_by_legacy_id(self, reference_id: str, *, environment: str) -> dict:
        refreshed = False
        max_attempts = max(1, int(self.settings.ebay_browse_max_retries))
        for attempt in range(1, max_attempts + 1):
            try:
                return self._request_item_by_legacy_id(reference_id, environment=environment)
            except BrowseApiError as exc:
                if exc.status_code == 401 and not refreshed:
                    self._app_token = None
                    self._app_token_expires_at = None
                    self._app_token_environment = None
                    refreshed = True
                    continue
                if exc.transient and attempt < max_attempts:
                    sleep(float(self.settings.ebay_browse_retry_base_seconds) * (2 ** (attempt - 1)))
                    continue
                raise
        raise BrowseApiError(None, None, 'retry limit exhausted', transient=True)

    def _request_item_by_legacy_id(self, reference_id: str, *, environment: str) -> dict:
        base_url = 'https://api.ebay.com/buy/browse/v1/item/get_item_by_legacy_id'
        if environment != 'PRODUCTION':
            base_url = 'https://api.sandbox.ebay.com/buy/browse/v1/item/get_item_by_legacy_id'
        request_url = f'{base_url}?{urlencode({"legacy_item_id": reference_id})}'
        try:
            token = self._get_app_token(environment=environment)
            request = Request(
                request_url,
                headers={
                    'Authorization': f'Bearer {token}',
                    'Accept': 'application/json',
                    'X-EBAY-C-MARKETPLACE-ID': self.settings.ebay_marketplace_id,
                },
                method='GET',
            )
            with urlopen(request, timeout=30) as response:
                payload = json.loads(response.read().decode('utf-8') or '{}')
        except HTTPError as exc:
            body = exc.read().decode('utf-8', errors='replace')
            payload = self._json_object(body)
            error_id, message = self._browse_error_details(payload, body)
            raise BrowseApiError(
                exc.code,
                error_id,
                message,
                payload,
                transient=exc.code == 429 or exc.code >= 500,
            ) from exc
        except (URLError, TimeoutError, json.JSONDecodeError) as exc:
            raise BrowseApiError(None, None, str(exc), transient=True) from exc
        if not isinstance(payload, dict):
            raise BrowseApiError(None, None, 'Browse API returned non-object payload')
        return payload

    def _get_app_token(self, *, environment: str) -> str:
        now = datetime.now(UTC)
        if (
            self._app_token
            and self._app_token_environment == environment
            and self._app_token_expires_at
            and self._app_token_expires_at > now + timedelta(minutes=2)
        ):
            return self._app_token

        token_url = 'https://api.ebay.com/identity/v1/oauth2/token'
        if environment != 'PRODUCTION':
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
        self._app_token_environment = environment
        self._app_token_expires_at = now + timedelta(seconds=int(payload.get('expires_in') or 7200))
        return self._app_token

    def _orders_changed_since(
        self,
        context: ConversationProductContext,
        conversation: Conversation,
    ) -> bool:
        if not context.last_enriched_at or not conversation.provider_account_id:
            return True
        account = self.db.get(EbayAccount, conversation.provider_account_id)
        last_order_sync_at = getattr(account, 'last_order_sync_at', None) if account else None
        return isinstance(last_order_sync_at, datetime) and last_order_sync_at > context.last_enriched_at

    def _find_cached_context(
        self,
        conversation: Conversation,
        reference_id: str,
    ) -> ConversationProductContext | None:
        if not conversation.provider_account_id:
            return None
        return self.db.scalar(
            select(ConversationProductContext)
            .join(Conversation, Conversation.id == ConversationProductContext.conversation_id)
            .where(Conversation.provider_account_id == conversation.provider_account_id)
            .where(ConversationProductContext.reference_id == reference_id)
            .where(ConversationProductContext.enrichment_status.in_(TERMINAL_ENRICHMENT_STATUSES))
            .where(ConversationProductContext.conversation_id != conversation.id)
            .order_by(ConversationProductContext.last_enriched_at.desc().nullslast())
            .limit(1)
        )

    def _copy_cached_context(
        self,
        source: ConversationProductContext,
        target: ConversationProductContext,
    ) -> None:
        target.item_title = source.item_title
        target.image_url = source.image_url
        target.seller_username = source.seller_username
        target.item_url = source.item_url
        target.price_value = source.price_value
        target.price_currency = source.price_currency
        target.offer_available = source.offer_available
        target.buy_now_available = source.buy_now_available
        target.cta_type = source.cta_type
        target.sku = source.sku
        target.order_id = source.order_id
        target.enrichment_status = source.enrichment_status
        target.raw_payload = source.raw_payload
        target.last_enriched_at = datetime.now(UTC)

    def _cache_key(self, conversation: Conversation, reference_id: str) -> tuple[str, str, str]:
        return (
            str(conversation.provider_account_id or ''),
            self._environment(conversation),
            reference_id,
        )

    def _environment(self, conversation: Conversation) -> str:
        if conversation.provider_account_id:
            account = self.db.get(EbayAccount, conversation.provider_account_id)
            if account:
                value = account.environment.value if hasattr(account.environment, 'value') else str(account.environment)
                return value.upper()
        return self.settings.ebay_environment.upper()

    def _json_object(self, body: str) -> object:
        try:
            return json.loads(body) if body else {}
        except json.JSONDecodeError:
            return {'raw_body': body}

    def _browse_error_details(self, payload: object, fallback: str) -> tuple[int | None, str]:
        if isinstance(payload, dict):
            errors = payload.get('errors')
            if isinstance(errors, list) and errors and isinstance(errors[0], dict):
                error = errors[0]
                error_id = error.get('errorId')
                try:
                    parsed_id = int(error_id) if error_id is not None else None
                except (TypeError, ValueError):
                    parsed_id = None
                return parsed_id, self._string(error.get('message')) or fallback
        return None, fallback or 'Unknown Browse API error'

    def _item_url(self, reference_id: str) -> str:
        return f'https://www.ebay.com/itm/{reference_id}'

    def _string(self, value: object) -> str | None:
        return value.strip() if isinstance(value, str) and value.strip() else None
