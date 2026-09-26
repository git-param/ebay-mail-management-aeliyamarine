"""Durable intent before dispatch; never retry an ambiguous response action."""
from datetime import UTC, datetime
from decimal import Decimal
import hashlib
import json
from sqlalchemy import select
from fastapi import HTTPException
from app.models.offer import Offer
from app.models.ebay_account import EbayAccount
from app.models.ebay_best_offer_action import EbayBestOfferAction
from app.modules.integrations.ebay.oauth.token_service import EbayTokenService
from app.modules.integrations.ebay.services.ebay_best_offer_query_service import actionable
from app.services.ebay_best_offer_lock import account_operation_lock
from app.services.ebay_api_usage_service import EbayApiUsageService
from app.services.permission_service import PermissionService
from app.services.audit_service import AuditService


def serialize_action(action):
    return {'id': action.id, 'offer_id': action.offer_id, 'action': action.action,
            'state': action.state, 'error': action.error, 'provider_result': action.provider_result,
            'created_at': action.created_at, 'completed_at': action.completed_at}


class EbayBestOfferActionService:
    def __init__(self, db):
        self.db = db

    def respond(self, offer_id, payload, user):
        PermissionService(self.db).ensure_user_has(user, 'offer.respond')
        parameters = payload.model_dump(mode='json', exclude={'idempotency_key'})
        digest = hashlib.sha256(json.dumps({'offer_id': str(offer_id), **parameters}, sort_keys=True).encode()).hexdigest()
        existing = self.db.scalar(select(EbayBestOfferAction).where(EbayBestOfferAction.idempotency_key == payload.idempotency_key))
        if existing:
            if existing.actor_id != user.id or existing.request_hash != digest:
                raise HTTPException(409, 'Idempotency key belongs to a different request')
            return serialize_action(existing)
        offer = self.db.get(Offer, offer_id)
        if not offer:
            raise HTTPException(404, 'Offer not found')
        account_id = offer.account_id
        self.db.rollback()
        with account_operation_lock(self.db.get_bind(), account_id):
            # Repeat key lookup under provider protection for browser/network races.
            existing = self.db.scalar(select(EbayBestOfferAction).where(EbayBestOfferAction.idempotency_key == payload.idempotency_key))
            if existing:
                if existing.actor_id != user.id or existing.request_hash != digest:
                    raise HTTPException(409, 'Idempotency key belongs to a different request')
                return serialize_action(existing)
            offer = self.db.scalar(select(Offer).where(Offer.id == offer_id).with_for_update())
            account = self.db.get(EbayAccount, account_id)
            latest = self.db.scalar(select(EbayBestOfferAction).where(EbayBestOfferAction.offer_id == offer_id)
                .order_by(EbayBestOfferAction.created_at.desc()).limit(1))
            if not account or not account.is_active or account.connection_status.value != 'CONNECTED':
                raise HTTPException(409, 'Account is not active and connected')
            if offer.version != payload.expected_version or not actionable(offer, latest):
                raise HTTPException(409, 'Offer changed, is not actionable, or requires reconciliation')
            raw = offer.provider_snapshot
            if payload.action == 'Counter' and payload.quantity > int(raw['quantity']):
                raise HTTPException(422, 'Counter quantity cannot exceed the verified offer quantity')
            listing = offer.listing_snapshot or {}
            if (payload.action == 'Counter' and payload.quantity == 1 and listing.get('price') is not None
                    and listing.get('currency') == raw.get('currency')
                    and payload.amount > Decimal(str(listing['price']))):
                raise HTTPException(422, 'Single-item counter price cannot exceed the available listing price')
            action = EbayBestOfferAction(offer_id=offer.id, account_id=account_id, actor_id=user.id,
                idempotency_key=payload.idempotency_key, request_hash=digest,
                expected_version=payload.expected_version, action=payload.action, parameters=parameters, state='PREPARED')
            self.db.add(action)
            self.db.commit()
            action_id = action.id
            usage = EbayApiUsageService(self.db)
            try:
                tokens = EbayTokenService(self.db)
                if account.environment.value != tokens.client.environment:
                    raise HTTPException(409, 'Account environment does not match the configured eBay OAuth environment')
                if not account.access_token or (account.access_token_expires_at and account.access_token_expires_at <= datetime.now(UTC)):
                    account = tokens.refresh_access_token(account.id)
                attempt = usage.reserve_attempt(account_id=account_id, operation='RespondToBestOffer', action_id=action_id)
                action.state = 'DISPATCHING'
                action.dispatched_at = datetime.now(UTC)
                offer.reconciliation_required = True
                offer.version += 1
                self.db.commit()
            except Exception:
                self.db.rollback()
                action = self.db.get(EbayBestOfferAction, action_id)
                action.state = 'FAILED'
                action.error = 'Pre-dispatch authorization/accounting failed; no response action sent'
                action.completed_at = datetime.now(UTC)
                AuditService(self.db).log(action='EBAY_BEST_OFFER_' + payload.action.upper(), user_id=user.id, entity_type='OFFER', entity_id=offer_id, category='OFFER_MANAGEMENT', metadata={'action_id': str(action_id), 'result': 'FAILED_BEFORE_DISPATCH', 'account_id': str(account_id)})
                self.db.commit()
                raise
            try:
                response = tokens.client.respond_to_best_offer_raw(account.access_token,
                    action=payload.action, offer_id=offer.provider_offer_id, item_id=offer.listing_id,
                    amount=payload.amount, quantity=payload.quantity, currency=raw['currency'],
                    message=payload.message, correlation_id=str(action.id))
                result = response.payload
                state = 'SUCCEEDED' if response.ok and result.get('confirmed') else (
                    'RECONCILIATION_REQUIRED' if result.get('ambiguous', True) else 'FAILED')
                usage.finish_attempt(attempt, state)
                action.state = state
                action.provider_result = result
                action.completed_at = datetime.now(UTC)
                if state == 'FAILED':
                    offer.reconciliation_required = False
                AuditService(self.db).log(action='EBAY_BEST_OFFER_' + payload.action.upper(),
                    user_id=user.id, entity_type='OFFER', entity_id=offer.id, category='OFFER_MANAGEMENT',
                    metadata={'action_id': str(action.id), 'result': state, 'account_id': str(account_id)})
                # Provider status changes only via authoritative GetBestOffers.
                self.db.commit()
            except Exception:
                self.db.rollback()
                action = self.db.get(EbayBestOfferAction, action_id)
                action.state = 'RECONCILIATION_REQUIRED'
                action.error = 'Provider result uncertain; action will not be resent automatically'
                self.db.get(Offer, offer_id).reconciliation_required = True
                AuditService(self.db).log(action='EBAY_BEST_OFFER_' + payload.action.upper(), user_id=user.id, entity_type='OFFER', entity_id=offer_id, category='OFFER_MANAGEMENT', metadata={'action_id': str(action_id), 'result': 'RECONCILIATION_REQUIRED', 'account_id': str(account_id)})
                self.db.commit()
                usage.finish_attempt(attempt, 'UNKNOWN')
            # A later scheduled/manual job reconciles this listing. No blind retry.
            return serialize_action(action)
