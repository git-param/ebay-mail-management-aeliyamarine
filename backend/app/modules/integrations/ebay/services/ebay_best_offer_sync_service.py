import logging
from datetime import UTC, datetime, timedelta
from decimal import Decimal, InvalidOperation
from time import perf_counter
from uuid import UUID, uuid4

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.conversation import Conversation
from app.models.ebay_account import EbayAccount
from app.models.ebay_best_offer_listing_sync_state import EbayBestOfferListingSyncState
from app.models.conversation import Message
from app.models.offer import Offer, OfferDirection, OfferStatus
from app.modules.integrations.ebay.services.ebay_offer_validation import (
    normalize_extracted_offer,
    update_missing_offer_fields,
)
from app.models.order_context import ConversationProductContext
from app.modules.integrations.ebay.oauth.token_service import EbayTokenService
from app.services.ebay_api_usage_service import EbayApiUsageService
from app.services.offer_consistency_service import OfferConsistencyService
from app.services.ebay_best_offer_lock import account_operation_lock
from fastapi import HTTPException

logger = logging.getLogger(__name__)

EMPTY_LISTING_RECHECK_AFTER = timedelta(hours=12)
OFFER_LISTING_RECHECK_AFTER = timedelta(hours=1)
RECENT_CONVERSATION_WINDOW = timedelta(days=30)


class EbayBestOfferSyncService:
    """Poll Trading API offers and materialize them without slowing conversation reads."""

    def __init__(self, db: Session):
        self.db = db
        self.tokens = EbayTokenService(db)
        self.api_usage = EbayApiUsageService(db)

    def sync_account(self, account_id: UUID, *, listing_ids: list[str] | None = None,  commit: bool = True) -> dict[str, int]:
        try:
            with account_operation_lock(self.db.get_bind(), account_id):
                return self._sync_listing_account(account_id, listing_ids=listing_ids, commit=commit)
        except HTTPException as exc:
            if exc.status_code != 409:
                raise
            # Best Offer contention must never fail the surrounding message sync.
            return dict(created=0, updated=0, linked=0, listings_checked=0, listings_skipped=1, api_calls=0, busy=True)

    def sync_current(self, account_id, *, job_id=None, should_stop=lambda: False):
        """Account discovery and selective history use the existing upsert path."""
        with account_operation_lock(self.db.get_bind(), account_id):
            account = self.db.get(EbayAccount, account_id)
            if not account or not account.is_active or account.connection_status.value != 'CONNECTED':
                raise ValueError('Account is not active and connected')
            if account.environment.value != self.tokens.client.environment:
                raise ValueError('Account environment does not match the configured eBay OAuth environment')
            if not account.access_token or (account.access_token_expires_at and account.access_token_expires_at <= datetime.now(UTC)):
                account = self.tokens.refresh_access_token(account.id)
            seen, count, errors = set(), 0, []
            discovery = {'pages': 0, 'returned': 0, 'seller': 0, 'buyer_skipped': 0, 'unknown_role_skipped': 0}
            def result(outcome):
                return {'offers_synced': count, 'outcome': outcome, 'errors': errors, 'discovery': discovery,
                    'scope': 'Active seller-side Trading Best Offers'}
            page = 1
            while True:
                if should_stop():
                    return result('STOPPED')
                payload = self._current_request(account, page=page, job_id=job_id)
                discovery['pages'] += 1
                for raw in payload.get('offers', []):
                    discovery['returned'] += 1
                    # Buyer/unknown roles are never admitted to seller operations.
                    if raw.get('role') != 'Seller':
                        discovery['buyer_skipped' if raw.get('role') == 'Buyer' else 'unknown_role_skipped'] += 1
                        continue
                    discovery['seller'] += 1
                    try:
                        with self.db.begin_nested():
                            conversation = self._match_conversation(account.id, raw.get('listingId'), raw.get('buyerUsername'))
                            offer, _ = self._upsert(account, raw, conversation)
                            offer.last_seen_sync_id = job_id
                            self.db.flush()
                            seen.add(offer.id)
                            self._upsert_derived_offer_events(account, raw, conversation, offer)
                            if conversation:
                                OfferConsistencyService(self.db).sync_conversation(conversation.id)
                        count += 1
                    except Exception as exc:
                        errors.append({'offer_id': raw.get('offerId'), 'error': type(exc).__name__})
                self.db.commit()
                if page >= max(1, int(payload.get('totalPages') or 1)):
                    break
                page += 1
            # Only a complete, error-free scan supplies absence evidence.
            if not errors:
                known = self.db.scalars(select(Offer).where(Offer.account_id == account.id,
                    Offer.record_source == 'TRADING', Offer.provider_role == 'Seller',
                    Offer.provider_status.in_(['Active','Pending','SellerAccept','PendingBuyerPayment','PendingBuyerConfirmation'])))
                for offer in known:
                    if offer.id not in seen or offer.provider_status in {'SellerAccept','PendingBuyerPayment','PendingBuyerConfirmation'}:
                        offer.reconciliation_required = True
                self.db.commit()
            now = datetime.now(UTC)
            listings = list(self.db.scalars(select(Offer.listing_id).where(
                Offer.account_id == account.id, Offer.record_source == 'TRADING',
                Offer.provider_role == 'Seller', Offer.reconciliation_required.is_(True),
                Offer.listing_id.is_not(None)).distinct()))
            for listing_id in listings:
                if should_stop():
                    return result('STOPPED')
                state = self._listing_state(account.id, listing_id, create=True)
                if state.next_reconcile_at and state.next_reconcile_at > now:
                    continue
                try:
                    self.reconcile_listing(account, listing_id, job_id=job_id, should_stop=should_stop)
                    state.last_reconciled_at = datetime.now(UTC)
                    state.next_reconcile_at = datetime.now(UTC) + timedelta(minutes=5)
                    state.reconcile_attempts = 0
                    state.last_error = None
                except Exception as exc:
                    self.db.rollback()
                    state = self._listing_state(account.id, listing_id, create=True)
                    state.reconcile_attempts += 1
                    state.next_reconcile_at = datetime.now(UTC) + timedelta(minutes=min(1440, 5 * 2 ** min(state.reconcile_attempts, 8)))
                    state.last_error = type(exc).__name__
                    errors.append({'listing_id': listing_id, 'error': type(exc).__name__})
                self.db.commit()
            return result('PARTIAL' if errors else 'SUCCESS')

    def _current_request(self, account, *, page=1, listing_id=None, job_id=None):
        for retry in range(2):
            attempt = self.api_usage.reserve_attempt(account_id=account.id, operation='GetBestOffers',
                job_id=job_id, attempt_number=retry + 1)
            try:
                response = self.tokens.client.get_best_offers_raw(account.access_token, page=page,
                    best_offer_status='All' if listing_id else 'Active', item_id=listing_id)
                self.api_usage.finish_attempt(attempt, 'SUCCESS' if response.ok else 'FAILED')
            except Exception:
                self.api_usage.finish_attempt(attempt, 'TRANSPORT_ERROR')
                raise
            if response.status_code == 401 and retry == 0:
                account = self.tokens.refresh_access_token(account.id)
                continue
            if not response.ok or response.payload.get('ack') not in {'Success','Warning'}:
                raise RuntimeError('GetBestOffers failed: ' + str(response.payload.get('errors') or response.payload.get('error')))
            if any(e.get('severity') == 'Error' for e in response.payload.get('errors', [])):
                raise RuntimeError('GetBestOffers returned provider errors')
            return response.payload
        raise RuntimeError('GetBestOffers authentication failed')

    def reconcile_listing(self, account, listing_id, *, job_id=None, should_stop=lambda: False):
        from app.models.ebay_best_offer_action import EbayBestOfferAction
        page = 1
        observed = []
        while True:
            if should_stop():
                raise RuntimeError('Automatic synchronization stopped')
            payload = self._current_request(account, page=page, listing_id=listing_id, job_id=job_id)
            for raw in payload.get('offers', []):
                raw['listingId'] = raw.get('listingId') or listing_id
                existing = self.db.scalar(select(Offer).where(Offer.account_id == account.id,
                    Offer.provider == 'EBAY', Offer.provider_offer_id == raw.get('offerId')))
                # Item-specific responses may omit Role. Only previously verified
                # identities can inherit their own role; new unknown rows fail closed.
                if not raw.get('role') and existing and existing.provider_role == 'Seller':
                    raw['role'] = 'Seller'
                if raw.get('role') != 'Seller':
                    continue
                with self.db.begin_nested():
                    offer, _ = self._upsert(account, raw, self._match_conversation(account.id, listing_id, raw.get('buyerUsername')))
                    offer.last_seen_sync_id = job_id
                    self.db.flush()
                    observed.append(offer.id)
                    self._upsert_derived_offer_events(account, raw, offer.conversation, offer)
            self.db.commit()
            if page >= max(1, int(payload.get('totalPages') or 1)):
                break
            page += 1
        for offer_id in observed:
            offer = self.db.get(Offer, offer_id)
            actions = self.db.scalars(select(EbayBestOfferAction).where(EbayBestOfferAction.offer_id == offer_id,
                EbayBestOfferAction.state.in_(['DISPATCHING','RECONCILIATION_REQUIRED','SUCCEEDED'])))
            awaiting_transition = False
            for action in actions:
                # Observing a provider transition closes ambiguity, without falsely
                # claiming that this user caused an externally made transition.
                if offer.provider_status in {'Active','Pending'}:
                    awaiting_transition = True
                else:
                    if action.state != 'SUCCEEDED':
                        action.state = 'RECONCILED'
                        action.completed_at = datetime.now(UTC)
                        action.provider_result = {'observed_status': offer.provider_status, 'result': 'Provider state observed; action attribution unknown'}
            offer.reconciliation_required = awaiting_transition or offer.provider_status in {'SellerAccept','PendingBuyerPayment','PendingBuyerConfirmation'}
        self.db.commit()

    def _sync_listing_account(self, account_id: UUID, *, listing_ids: list[str] | None = None, commit: bool = True):
        account = self.db.get(EbayAccount, account_id)
        if not account or not account.is_active:
            raise ValueError('Active eBay account not found')
        if not account.access_token or (account.access_token_expires_at and account.access_token_expires_at <= datetime.now(UTC)):
            account = self.tokens.refresh_access_token(account.id)

        sync_operation_id = str(uuid4())
        created = updated = linked = listings_checked = listings_skipped = api_calls = 0
        touched_conversation_ids = set()
        started_at = perf_counter()
        
        # Determine candidates
        if listing_ids is not None:
            # Build candidates from the provided listing_ids
            candidates = [
                {
                    "listing_id": lid,
                    "activity_at": None, 
                    "conversation_count": 0,
                }
                for lid in set(listing_ids) if lid
            ]
        else:
            candidates = self._conversation_listing_candidates(account.id)

        logger.warning(
            "BestOffer sync started operation_id=%s account_id=%s candidate_listings=%s strategy=conversation_listing_full_scan",
            sync_operation_id,
            account.id,
            len(candidates),
        )

        for candidate in candidates:
            listing_id = candidate["listing_id"]
            
            listings_checked += 1
            page = 1
            listing_offer_count = 0
            listing_error = None
            while True:
                api_calls += 1
                payload = self._get_listing_best_offers(
                    account,
                    listing_id,
                    page,
                    sync_operation_id=sync_operation_id,
                    request_number=api_calls,
                )
                offers = payload.get("offers", []) if isinstance(payload.get("offers"), list) else []
                total_pages = max(int(payload.get('totalPages') or 1), 1)
                listing_offer_count += len(offers)
                listing_error = payload.get("error")

                logger.warning(
                    "BestOffer page processed operation_id=%s account_id=%s listing_id=%s page=%s total_pages=%s offers_count=%s",
                    sync_operation_id,
                    account.id,
                    listing_id,
                    page,
                    total_pages,
                    len(offers),
                )

                for raw in offers:
                    conversation = None
                    raw['listingId'] = raw.get('listingId') or listing_id
                    try:
                        with self.db.begin_nested():
                            conversation = self._match_conversation(
                                account.id,
                                raw.get('listingId') or listing_id,
                                raw.get('buyerUsername'),
                            )
                            result, was_created = self._upsert(account, raw, conversation)
                            derived_results = self._upsert_derived_offer_events(account, raw, conversation, result)
                            touched_conversation_ids.update(
                                value
                                for value in (
                                    getattr(conversation, "id", None),
                                    result.conversation_id,
                                    *(offer.conversation_id for offer, _ in derived_results),
                                )
                                if value
                            )
                            created += int(was_created)
                            updated += int(not was_created)
                            linked += int(result.conversation_id is not None)
                            created += sum(int(was_created) for _, was_created in derived_results)
                            updated += sum(int(not was_created) for _, was_created in derived_results)
                            linked += sum(int(offer.conversation_id is not None) for offer, _ in derived_results)
                    except IntegrityError:
                        logger.exception(
                            "Best offer upsert failed but sync will continue. account_id=%s "
                            "conversation_id=%s message_id=%s provider_offer_id=%s payload=%s",
                            account.id,
                            getattr(conversation, "id", None),
                            None,
                            raw.get("offerId") if isinstance(raw, dict) else None,
                            raw,
                        )
                    except ValueError as exc:
                        logger.warning(
                            "Skipping incomplete best offer. reason=%s account_id=%s conversation_id=%s "
                            "message_id=%s provider_offer_id=%s payload=%s",
                            exc,
                            account.id,
                            getattr(conversation, "id", None),
                            None,
                            raw.get("offerId") if isinstance(raw, dict) else None,
                            raw,
                        )
                    except Exception:
                        logger.exception(
                            "Unexpected best offer upsert error but sync will continue. account_id=%s "
                            "conversation_id=%s message_id=%s provider_offer_id=%s payload=%s",
                            account.id,
                            getattr(conversation, "id", None),
                            None,
                            raw.get("offerId") if isinstance(raw, dict) else None,
                            raw,
                        )

                if page >= total_pages:
                    break
                page += 1
            self._update_listing_state(account.id, candidate, listing_offer_count, listing_error)

        logger.warning(
            "BestOffer sync finished operation_id=%s account_id=%s listings_checked=%s listings_skipped=%s "
            "created=%s updated=%s linked=%s total_outbound_ebay_api_calls=%s elapsed_seconds=%.2f",
            sync_operation_id,
            account.id,
            listings_checked,
            listings_skipped,
            created,
            updated,
            linked,
            api_calls,
            perf_counter() - started_at,
        )
        OfferConsistencyService(self.db).sync_conversations(touched_conversation_ids)
        if commit:
            self.db.commit()
        else:
            self.db.flush()
        return {
            'created': created,
            'updated': updated,
            'linked': linked,
            'listings_checked': listings_checked,
            'listings_skipped': listings_skipped,
            'api_calls': api_calls,
        }

    def _get_listing_best_offers(
        self,
        account: EbayAccount,
        listing_id: str,
        page: int,
        *,
        sync_operation_id: str,
        request_number: int,
    ) -> dict:
        retry_count = 0
        started_at = perf_counter()
        for retry_count in range(2):
            attempt = self.api_usage.reserve_attempt(account_id=account.id, operation='GetBestOffers', attempt_number=retry_count + 1)
            try:
                response = self.tokens.client.get_best_offers_raw(account.access_token,
                    page=page, best_offer_status='All', item_id=listing_id)
                self.api_usage.finish_attempt(attempt, 'SUCCESS' if response.ok else 'FAILED')
            except Exception:
                self.api_usage.finish_attempt(attempt, 'TRANSPORT_ERROR')
                raise
            if response.status_code == 401 and retry_count == 0:
                account = self.tokens.refresh_access_token(account.id)
                continue
            break
        duration = perf_counter() - started_at
        payload = response.payload if isinstance(response.payload, dict) else {}
        offers = payload.get("offers", []) if isinstance(payload.get("offers"), list) else []
        rate_limit = self._rate_limit_headers(response.response_headers or {})
        logger.warning(
            "BestOffer API operation_id=%s endpoint=Trading.GetBestOffers account_id=%s listing_id=%s "
            "request_number=%s page=%s response_status=%s ack=%s offers_count=%s total_pages=%s "
            "retry_count=%s duration_seconds=%.2f rate_limit=%s",
            sync_operation_id,
            account.id,
            listing_id,
            request_number,
            page,
            response.status_code,
            payload.get("ack"),
            len(offers),
            payload.get("totalPages"),
            retry_count,
            duration,
            rate_limit,
        )
        if not response.ok:
            error = str(payload.get('error') if isinstance(payload, dict) else 'GetBestOffers failed')
            empty_listing_errors = (
                'no best offers found',
                'not best offer enabled',
                'best offer is not enabled',
            )
            if any(fragment in error.lower() for fragment in empty_listing_errors):
                return {'offers': [], 'totalPages': 1, 'error': error, 'ack': 'Failure'}
            raise RuntimeError(error)
        return payload

    def _conversation_listing_candidates(self, account_id: UUID) -> list[dict]:
        rows = self.db.execute(
            select(
                Conversation.reference_id,
                func.max(func.coalesce(Conversation.last_message_at, Conversation.external_created_at, Conversation.created_at)),
                func.count(Conversation.id),
            )
            .where(
                Conversation.provider_account_id == account_id,
                Conversation.provider_conversation_type == 'FROM_MEMBERS',
                Conversation.reference_id.is_not(None),
            )
            .group_by(Conversation.reference_id)
            .order_by(func.max(func.coalesce(Conversation.last_message_at, Conversation.external_created_at, Conversation.created_at)).desc())
        )
        seen = set()
        candidates = []
        for listing_id_value, activity_at, conversation_count in rows:
            listing_id = str(listing_id_value or '').strip()
            if not listing_id or listing_id in seen:
                continue
            seen.add(listing_id)
            candidates.append(
                {
                    "listing_id": listing_id,
                    "activity_at": activity_at,
                    "conversation_count": int(conversation_count or 0),
                }
            )
        return candidates
    
    def _needs_seller_counteroffer_repair(self, account_id: UUID, listing_id: str) -> bool:
        accepted_counteroffers = list(
            self.db.scalars(
                select(Offer).where(
                    Offer.provider == "EBAY",
                    Offer.account_id == account_id,
                    Offer.listing_id == listing_id,
                    Offer.offer_type == "SELLER_COUNTEROFFER",
                    Offer.status == OfferStatus.ACCEPTED,
                )
            )
        )
        for offer in accepted_counteroffers:
            derived_id = f"{offer.provider_offer_id}:seller-counteroffer-submitted"
            exists = self.db.scalar(
                select(Offer.id)
                .where(
                    Offer.provider == "EBAY",
                    Offer.account_id == account_id,
                    Offer.provider_offer_id == derived_id,
                )
                .limit(1)
            )
            if not exists:
                return True
        return False

    def _update_listing_state(self, account_id: UUID, candidate: dict, offer_count: int, error: str | None) -> None:
        now = datetime.now(UTC)
        state = self._listing_state(account_id, candidate["listing_id"], create=True)
        state.last_checked_at = now
        state.last_conversation_activity_at = candidate.get("activity_at")
        state.last_offer_count = offer_count
        state.last_error = error
        if offer_count:
            state.last_offer_seen_at = now
            state.last_empty_at = None
        else:
            state.last_empty_at = now

    def _listing_state(
        self,
        account_id: UUID,
        listing_id: str,
        *,
        create: bool = False,
    ) -> EbayBestOfferListingSyncState | None:
        state = self.db.scalar(
            select(EbayBestOfferListingSyncState).where(
                EbayBestOfferListingSyncState.account_id == account_id,
                EbayBestOfferListingSyncState.listing_id == listing_id,
            )
        )
        if state or not create:
            return state
        state = EbayBestOfferListingSyncState(account_id=account_id, listing_id=listing_id)
        self.db.add(state)
        return state

    def _extract_currency(self, raw: dict) -> str | None:
        amount_obj = raw.get("amount")
        if isinstance(amount_obj, dict):
            return amount_obj.get("currencyId") or amount_obj.get("currencyID")
        # Fallback to a top-level currency field (just in case)
        return raw.get("currency")

    def _upsert(self, account: EbayAccount, raw: dict, conversation: Conversation | None) -> tuple[Offer, bool]:
        normalized_offer, skip_reason = normalize_extracted_offer(
            {
                "provider_offer_id": raw.get("offerId"),
                "listing_id": raw.get("listingId"),
                "buyer_username": raw.get("buyerUsername"),
                "offer_amount": self._decimal(raw.get("amount")),
                "currency": self._extract_currency(raw),
                "status": self._status(raw.get("status")),
                "direction": self._direction(raw.get("offerType"), raw.get("status")),
                "offer_type": self._offer_type(raw.get("offerType")),
                "quantity": raw.get("quantity"),
                "raw_text": raw.get("sellerMessage") or raw.get("buyerMessage"),
                "expires_at": self._datetime(raw.get("expirationTime")),
                "created_at_provider": self._datetime(raw.get("createdTime")),
                "raw_payload": raw,
            },
            account=account,
            logger=logger,
        )
        if skip_reason:
            logger.warning(
                "Skipping incomplete best offer. reason=%s account_id=%s conversation_id=%s "
                "message_id=%s provider_offer_id=%s payload=%s",
                skip_reason,
                account.id,
                getattr(conversation, "id", None),
                None,
                raw.get("offerId"),
                raw,
            )
            raise ValueError(f"Skipping incomplete best offer: {skip_reason}")

        provider_id = normalized_offer["provider_offer_id"]
        listing_id = str(raw.get('listingId') or '').strip()

        if not provider_id or not listing_id:
            raise ValueError('GetBestOffers response omitted offer or listing ID')

        offer = self.db.scalar(
            select(Offer).where(
                Offer.provider == "EBAY",
                Offer.account_id == account.id,
                Offer.provider_offer_id == provider_id,
            )
        )
        created = offer is None

        if offer is None:
            offer = Offer(
                provider="EBAY",
                account_id=account.id,
                provider_offer_id=provider_id,
                listing_id=listing_id,
                conversation_id=conversation.id if conversation else None,
                buyer_username=normalized_offer.get("buyer_username"),
                offer_amount=normalized_offer.get("offer_amount"),
                currency=normalized_offer.get("currency"),
                status=normalized_offer.get("status"),
                direction=normalized_offer.get("direction"),
                offer_type=normalized_offer.get("offer_type"),
                quantity=normalized_offer.get("quantity"),
                raw_text=normalized_offer.get("raw_text"),
                expires_at=normalized_offer.get("expires_at"),
                created_at_provider=normalized_offer.get("created_at_provider"),
                raw_payload=normalized_offer.get("raw_payload"),
            )
            self.db.add(offer)

        # Use only an exact FROM_MEMBERS conversation match.
        offer.provider = "EBAY"
        offer.account_id = account.id
        offer.conversation_id = conversation.id if conversation and conversation.provider_conversation_type == 'FROM_MEMBERS' else None
        update_missing_offer_fields(
            offer,
            normalized_offer,
            fields=(
                "listing_id",
                "buyer_username",
                "offer_amount",
                "currency",
                "status",
                "direction",
                "offer_type",
                "quantity",
                "raw_text",
                "expires_at",
                "created_at_provider",
                "raw_payload",
            ),
        )
        if raw.get('derivedEvent') or str(provider_id).endswith(':seller-counteroffer-submitted'):
            offer.record_source = 'DERIVED'
        else:
            now = datetime.now(UTC)
            if offer.provider_snapshot != raw:
                offer.version = (offer.version or 1) + (0 if created else 1)
            offer.record_source = 'TRADING'
            offer.provider_status = raw.get('status')
            offer.provider_role = raw.get('role') or offer.provider_role
            offer.provider_snapshot = dict(raw)
            offer.listing_snapshot = {**(offer.listing_snapshot or {}), **self._listing_metadata(account.id, offer.listing_id), **{k: v for k, v in (raw.get('listing') or {}).items() if v is not None}}
            offer.last_seen_at = now
            offer.last_synced_at = now
        if conversation:
            self._attach_matching_message(offer, conversation)

        return offer, created

    def _listing_metadata(self, account_id, listing_id):
        # Cached metadata must match both account and item, never another seller.
        context = self.db.scalar(select(ConversationProductContext).join(Conversation,
            Conversation.id == ConversationProductContext.conversation_id).where(
            Conversation.provider_account_id == account_id,
            ConversationProductContext.reference_id == listing_id)
            .order_by(ConversationProductContext.updated_at.desc()).limit(1))
        if not context:
            return {}
        data = {'title': context.item_title, 'image_url': context.image_url, 'sku': context.sku,
                'price': str(context.price_value) if context.price_value is not None else None,
                'currency': context.price_currency}
        payload = context.raw_payload or {}
        condition = payload.get('condition')
        if isinstance(condition, str):
            data['condition'] = condition
        return {k: v for k, v in data.items() if v is not None}

    def _upsert_derived_offer_events(
        self,
        account: EbayAccount,
        raw: dict,
        conversation: Conversation | None,
        source_offer: Offer,
    ) -> list[tuple[Offer, bool]]:
        if raw.get("offerType") != "SellerCounterOffer":
            return []
        if source_offer.status != OfferStatus.ACCEPTED:
            return []

        submitted_raw = dict(raw)
        submitted_raw["offerId"] = f"{raw.get('offerId')}:seller-counteroffer-submitted"
        submitted_raw["status"] = "Active"
        submitted_raw.pop("createdTime", None)
        submitted_raw["derivedFromOfferId"] = raw.get("offerId")
        submitted_raw["derivedEvent"] = "SELLER_COUNTEROFFER_SUBMITTED"
        submitted_raw["derivedReason"] = "Accepted SellerCounterOffer also represents the earlier sent counteroffer event"

        offer, created = self._upsert(account, submitted_raw, conversation)
        if conversation:
            self._attach_seller_counteroffer_message(offer, conversation)
        return [(offer, created)]

    def _sync_seller_offer_response(self, account: EbayAccount, offer: Offer):
        """
        Sync the seller's response to an offer if it exists.
        This creates a message in the conversation with the seller's offer details.
        """
        try:
            # Get the offer details from eBay to check for seller responses
            self.api_usage.reserve_calls(1, EbayApiUsageService.BESTSELLER)
            response = self.tokens.client.get_offer_details_raw(
                account.access_token,
                offer_id=offer.provider_offer_id
            )
            
            if response.status_code == 401:
                account = self.tokens.refresh_access_token(account.id)
                self.api_usage.reserve_calls(1, EbayApiUsageService.BESTSELLER)
                response = self.tokens.client.get_offer_details_raw(
                    account.access_token,
                    offer_id=offer.provider_offer_id
                )
            
            if response.ok and isinstance(response.payload, dict):
                offer_detail = response.payload
                
                # Check if seller responded with a counter-offer
                if 'sellerResponse' in offer_detail:
                    seller_response = offer_detail['sellerResponse']
                    
                    # Create or update the seller's offer message
                    from app.models.message import Message
                    from app.models.message_direction import MessageDirection
                    
                    # Check if we already have a message for this response
                    existing_message = self.db.scalar(
                        select(Message).where(
                            Message.conversation_id == offer.conversation_id,
                            Message.provider_message_id == seller_response.get('responseId'),
                            Message.sender_type == 'SELLER'
                        )
                    )
                    
                    if not existing_message:
                        seller_message = Message(
                            conversation_id=offer.conversation_id,
                            provider_message_id=seller_response.get('responseId'),
                            sender_type='SELLER',
                            sender_identifier=account.ebay_username,
                            body=seller_response.get('message', f"Counter-offer: ${seller_response.get('amount')}"),
                            is_inbound=False,  # Outgoing from seller
                            direction=MessageDirection.OUTGOING,
                            sent_at=self._datetime(seller_response.get('createdDate')) or datetime.now(UTC),
                            raw_payload=seller_response,
                        )
                        self.db.add(seller_message)
                        
                        seller_message.offer_data = None
                        logger.warning(
                            'Created seller offer response message for conversation %s offer %s',
                            offer.conversation_id,
                            offer.provider_offer_id
                        )
        except Exception as e:
            logger.warning('Failed to sync seller offer response: %s', e)

    # In ebay_best_offer_sync_service.py
    def _match_conversation(self, account_id: UUID, listing_id: str, buyer: str) -> Conversation | None:
        buyer = str(buyer or '').strip()
        listing_id = str(listing_id or '').strip()
        if not listing_id:
            return None
        
        statement = select(Conversation).where(
            Conversation.provider_account_id == account_id,
            Conversation.provider_conversation_type == 'FROM_MEMBERS',
            Conversation.reference_id == listing_id,
        )
        if buyer:
            exact = self.db.scalar(statement.where(func.lower(Conversation.buyer_identifier) == buyer.lower()))
            if exact:
                return exact

        candidates = list(self.db.scalars(statement))
        if len(candidates) == 1:
            return candidates[0]
        return None

    def _status(self, value) -> OfferStatus:
        normalized = str(value or 'Pending').upper()
        return {
            'ACTIVE': OfferStatus.PENDING, 'PENDING': OfferStatus.PENDING,
            'COUNTERED': OfferStatus.COUNTERED,
            'ACCEPTED': OfferStatus.ACCEPTED, 'DECLINED': OfferStatus.DECLINED,
            'EXPIRED': OfferStatus.EXPIRED, 'WITHDRAWN': OfferStatus.RETRACTED,
            'RETRACTED': OfferStatus.RETRACTED,
        }.get(normalized, OfferStatus.PENDING)

    def _direction(self, value, status=None) -> str:
        if self._status(status) == OfferStatus.ACCEPTED:
            return OfferDirection.INCOMING
        normalized = str(value or '').upper()
        if normalized == 'SELLERCOUNTEROFFER':
            return OfferDirection.OUTGOING
        return OfferDirection.INCOMING

    def _offer_type(self, value) -> str:
        normalized = str(value or '').upper()
        if normalized == 'SELLERCOUNTEROFFER':
            return 'SELLER_COUNTEROFFER'
        if normalized == 'BUYERCOUNTEROFFER':
            return 'BUYER_COUNTEROFFER'
        return 'BUYER_OFFER'

    def _decimal(self, value):
        try:
            return Decimal(str(value)) if value is not None else None
        except InvalidOperation:
            return None

    def _datetime(self, value):
        try:
            return self._aware(datetime.fromisoformat(str(value).replace('Z', '+00:00'))) if value else None
        except ValueError:
            return None

    def _aware(self, value):
        if not value:
            return None
        if value.tzinfo is None:
            return value.replace(tzinfo=UTC)
        return value.astimezone(UTC)

    def _attach_matching_message(self, offer: Offer, conversation: Conversation) -> None:
        messages = list(
            self.db.scalars(
                select(Message)
                .where(Message.conversation_id == conversation.id)
                .order_by(Message.sent_at.asc(), Message.created_at.asc())
            )
        )
        match = self._matching_offer_message(offer, messages)
        if not match:
            return
        if self._is_offer_notification_message(match):
            offer.message_id = match.id
        if not offer.created_at_provider:
            offer.created_at_provider = match.sent_at

    def _matching_offer_message(self, offer: Offer, messages: list[Message]) -> Message | None:
        amount = self._decimal(offer.offer_amount)
        currency = str(offer.currency or '').upper()
        preferred = []
        fallback = []
        for message in messages:
            text = " ".join(str(part or "") for part in (message.body, message.raw_payload if isinstance(message.raw_payload, dict) else ""))
            lower = text.lower()
            if amount is not None:
                message_amount, message_currency = self._extract_money(text)
                if message_amount != amount:
                    continue
                if message_currency and currency and message_currency != currency:
                    continue

            if offer.status == OfferStatus.ACCEPTED and "accepted" in lower:
                preferred.append(message)
                continue
            if offer.offer_type == "SELLER_COUNTEROFFER" and ("you sent a counteroffer" in lower or "counteroffer" in lower):
                preferred.append(message)
                continue
            if offer.offer_type == "BUYER_COUNTEROFFER" and "counteroffer" in lower:
                preferred.append(message)
                continue
            if offer.offer_type == "BUYER_OFFER" and "offer" in lower:
                fallback.append(message)
        return preferred[-1] if preferred else (fallback[-1] if fallback else None)

    def _attach_seller_counteroffer_message(self, offer: Offer, conversation: Conversation) -> None:
        messages = list(
            self.db.scalars(
                select(Message)
                .where(Message.conversation_id == conversation.id)
                .order_by(Message.sent_at.asc(), Message.created_at.asc())
            )
        )
        raw_text = " ".join(str(offer.raw_text or "").split()).lower()
        for message in messages:
            if message.is_inbound:
                continue
            body = " ".join(str(message.body or "").split()).lower()
            if raw_text and body and body == raw_text:
                if self._is_offer_notification_message(message):
                    offer.message_id = message.id
                if not offer.created_at_provider:
                    offer.created_at_provider = message.sent_at
                return


    def _is_offer_notification_message(self, message: Message) -> bool:
        offer_data = message.offer_data if isinstance(message.offer_data, dict) else {}
        raw_payload = message.raw_payload if isinstance(message.raw_payload, dict) else {}
        raw_source = raw_payload.get("source")
        return offer_data.get("notification_type") == "OFFER" or raw_source == "ufe_conversation_offer_card"

    def _extract_money(self, text: str):
        import re

        patterns = (
            r"\b(?P<currency>USD|EUR|GBP|AUD|CAD|JPY|INR)\s*(?P<amount>[\d,]+(?:\.\d{1,2})?)",
            r"\b(?P<currency>AU)\s*\$\s*(?P<amount>[\d,]+(?:\.\d{1,2})?)",
            r"\bUS\s*\$\s*(?P<amount>[\d,]+(?:\.\d{1,2})?)",
            r"€\s*(?P<amount>[\d,]+(?:\.\d{1,2})?)",
            r"£\s*(?P<amount>[\d,]+(?:\.\d{1,2})?)",
            r"\$\s*(?P<amount>[\d,]+(?:\.\d{1,2})?)",
        )
        for pattern in patterns:
            match = re.search(pattern, text or "", re.IGNORECASE)
            if not match:
                continue
            raw_amount = match.groupdict().get("amount")
            raw_currency = match.groupdict().get("currency")
            matched = match.group(0)
            if not raw_currency:
                raw_currency = "EUR" if "€" in matched else "GBP" if "£" in matched else "USD"
            raw_currency = raw_currency.upper()
            if raw_currency == "AU":
                raw_currency = "AUD"
            try:
                return Decimal(raw_amount.replace(",", "")), raw_currency
            except (InvalidOperation, AttributeError):
                return None, None
        return None, None

    def _rate_limit_headers(self, headers: dict[str, str]) -> dict[str, str]:
        return {
            key: value
            for key, value in headers.items()
            if "limit" in key.lower() or "remaining" in key.lower() or "reset" in key.lower()
        }
