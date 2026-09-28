"""Verified offer events supply listing IDs to the existing sync worker."""
import base64
import hashlib
import json
import logging
import re
import secrets
from datetime import UTC, datetime, timedelta
from urllib.parse import quote

import requests
from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from fastapi import HTTPException
from sqlalchemy import select

from app.core.config import get_settings
from app.models.app_config import AppConfigSetting
from app.models.conversation import SyncLog, SyncLogStatus
from app.models.ebay_account import EbayAccount
from app.modules.integrations.ebay.oauth.token_service import EbayTokenService
from app.services.ebay_best_offer_lock import account_operation_lock

EVENT = 'EBAY_OFFER_ACTIVITY'
PREFIX = 'offer.activity.'
_TOKEN_CACHE = {}
_KEY_CACHE = {}
logger = logging.getLogger(__name__)


def verify_signature(body, header, public_key):
    try:
        signature = json.loads(base64.b64decode(header, validate=True))
        key = serialization.load_pem_public_key(public_key.encode())
        if not isinstance(key, ec.EllipticCurvePublicKey):
            raise ValueError('Expected ECC key')
        key.verify(base64.b64decode(signature['signature'], validate=True), body, ec.ECDSA(hashes.SHA1()))
    except (ValueError, TypeError, KeyError, InvalidSignature):
        raise HTTPException(412, 'Invalid eBay notification signature') from None


class EbayOfferActivityService:
    def __init__(self, db):
        self.db = db
        self.client = EbayTokenService(db).client
        host = 'api.ebay.com' if self.client.environment == 'PRODUCTION' else 'api.sandbox.ebay.com'
        self.base = f'https://{host}/commerce/notification/v1'
        self._app_token = None

    def settings(self, account_id, create=False):
        row = self.db.scalar(select(AppConfigSetting).where(AppConfigSetting.config_key == PREFIX+str(account_id)))
        if row is None and create:
            row = AppConfigSetting(config_key=PREFIX+str(account_id), section='offer',
                label='Offer activity subscription', value=json.dumps({'verification_token': secrets.token_urlsafe(48)}),
                value_type='json', is_editable=False)
            self.db.add(row)
            self.db.commit()
        return row

    def endpoint(self, account_id):
        base = get_settings().public_backend_url.rstrip('/')
        if not base.startswith('https://'):
            raise HTTPException(422, 'PUBLIC_BACKEND_URL must expose this backend over HTTPS')
        return f'{base}/api/v1/integrations/ebay/best-offers/activity/{account_id}'

    def challenge(self, account_id, code):
        row = self.settings(account_id)
        if not row:
            raise HTTPException(404, 'Offer activity destination is not configured')
        settings = json.loads(row.value)
        endpoint = settings.get('endpoint') or self.endpoint(account_id)
        return {'challengeResponse': hashlib.sha256((code+settings['verification_token']+endpoint).encode()).hexdigest()}

    def app_token(self):
        cache_key = (self.client.client_id, self.client.environment)
        cached = _TOKEN_CACHE.get(cache_key)
        if cached and cached[1] > datetime.now(UTC):
            return cached[0]
        token = self.client._request_tokens({'grant_type': 'client_credentials',
            'scope': 'https://api.ebay.com/oauth/api_scope'})
        if len(_TOKEN_CACHE) >= 8:
            _TOKEN_CACHE.clear()
        _TOKEN_CACHE[cache_key] = (token.access_token, datetime.now(UTC)+timedelta(seconds=max(0, (token.expires_in or 0)-60)))
        return token.access_token

    def request(self, method, path, token, payload=None):
        try:
            response = requests.request(method, self.base+path, headers={'Authorization': 'Bearer '+token},
                json=payload, timeout=30)
        except requests.RequestException:
            raise HTTPException(502, 'Unable to reach eBay notification service') from None
        if not response.ok:
            # Preserve provider diagnostics without logging credentials or request bodies.
            try:
                errors = response.json().get('errors', [])
            except (ValueError, AttributeError):
                errors = []
            details = []
            for error in errors[:3] if isinstance(errors, list) else []:
                if isinstance(error, dict):
                    message = str(error.get('message') or 'No error message supplied')
                    message = ' '.join(message.split())[:500].replace(token, '[redacted]') if token else ' '.join(message.split())[:500]
                    code = error.get('errorId')
                    code = str(code) if isinstance(code, int) else 'unknown'
                    details.append(f'{code}: {message}')
            detail = f'eBay notification request failed: {method} {path} (HTTP {response.status_code})'
            if details:
                detail += '. ' + '; '.join(details)
            logger.warning('%s', detail)
            raise HTTPException(502, detail)
        return response.json() if response.content else {}, response.headers

    def setup(self, account_id):
        account = self.db.get(EbayAccount, account_id)
        if not account or not account.is_active or account.connection_status.value != 'CONNECTED':
            raise HTTPException(422, 'Select a connected account')
        if account.environment.value != self.client.environment:
            raise HTTPException(422, 'Account environment does not match configuration')
        with account_operation_lock(self.db.get_bind(), account_id):
            row = self.settings(account_id, create=True)
            settings = json.loads(row.value)
            endpoint = self.endpoint(account_id)
            if settings.get('endpoint') and settings['endpoint'] != endpoint:
                raise HTTPException(409, 'The public endpoint changed. Reconfigure the existing destination in eBay before subscribing.')
            settings['endpoint'] = endpoint
            row.value = json.dumps(settings)
            self.db.commit()  # eBay's challenge arrives through a separate session.
            if not settings.get('destination_id'):
                _, headers = self.request('POST', '/destination', self.app_token(),
                    {'name': 'ACES offers '+str(account_id), 'status': 'ENABLED',
                     'deliveryConfig': {'endpoint': endpoint, 'verificationToken': settings['verification_token']}})
                location = headers.get('Location') or headers.get('location')
                if not location:
                    raise HTTPException(502, 'eBay did not return a destination ID')
                settings['destination_id'] = location.rstrip('/').rsplit('/', 1)[-1]
                row.value = json.dumps(settings)
                self.db.commit()
            if not settings.get('subscription_id'):
                if not account.access_token_expires_at or account.access_token_expires_at <= datetime.now(UTC):
                    account = EbayTokenService(self.db).refresh_access_token(account_id)
                _, headers = self.request('POST', '/subscription', account.access_token,
                    {'topicId': 'OFFER_ACTIVITY', 'status': 'ENABLED', 'destinationId': settings['destination_id'],
                     'payload': {'format': 'JSON', 'schemaVersion': '1.0', 'deliveryProtocol': 'HTTPS'}})
                location = headers.get('Location') or headers.get('location')
                if not location:
                    raise HTTPException(502, 'eBay did not return a subscription ID')
                settings['subscription_id'] = location.rstrip('/').rsplit('/', 1)[-1]
                row.value = json.dumps(settings)
                self.db.commit()
            return {'account_id': account_id, 'status': 'ENABLED', 'endpoint': endpoint}

    def receive(self, account_id, body, header):
        row = self.settings(account_id)
        if not row or not json.loads(row.value).get('subscription_id'):
            raise HTTPException(404, 'Offer activity subscription is not enabled')
        try:
            signature = json.loads(base64.b64decode(header or '', validate=True))
            kid = signature['kid']
            if not isinstance(kid, str) or not re.fullmatch(r'[A-Za-z0-9_-]{1,128}', kid):
                raise ValueError('Invalid public key ID')
        except (ValueError, KeyError, TypeError):
            raise HTTPException(412, 'Invalid eBay signature header') from None
        cache_key = (self.client.environment, kid)
        cached = _KEY_CACHE.get(cache_key)
        if cached and cached[1] > datetime.now(UTC):
            public_key = cached[0]
        else:
            public_key, _ = self.request('GET', '/public_key/'+quote(kid, safe=''), self.app_token())
            if len(_KEY_CACHE) >= 128:
                _KEY_CACHE.clear()
            _KEY_CACHE[cache_key] = (public_key, datetime.now(UTC)+timedelta(hours=1))
        verify_signature(body, header, public_key['key'])
        try:
            payload = json.loads(body)
        except (ValueError, UnicodeError):
            raise HTTPException(422, 'Invalid notification JSON') from None
        return self.enqueue(account_id, payload)

    def enqueue(self, account_id, payload):
        if payload.get('metadata', {}).get('topic') != 'OFFER_ACTIVITY':
            raise HTTPException(422, 'Expected OFFER_ACTIVITY notification')
        notification = payload.get('notification', {})
        data = notification.get('data', {})
        event_id, item_id = notification.get('notificationId'), data.get('itemId')
        if not isinstance(event_id, str) or not 1 <= len(event_id) <= 255 or not re.fullmatch(r'\d{1,32}', str(item_id or '')):
            raise HTTPException(422, 'Notification omitted event or item identity')
        account = self.db.get(EbayAccount, account_id)
        if not account or not account.is_active or account.environment.value != self.client.environment:
            raise HTTPException(422, 'Notification account is unavailable')
        role = None
        for key, value in [('seller', 'Seller'), ('buyer', 'Buyer')]:
            user = data.get(key) or {}
            username = user.get('username') or user.get('userName')
            if (username and username.strip().casefold() == account.ebay_username.strip().casefold()) or (
                account.ebay_user_id and user.get('userId') == account.ebay_user_id):
                role = value
        if not role:
            raise HTTPException(422, 'Notification user does not match the subscribed account')
        # Event delivery must not wait behind a long-running provider sync.
        with account_operation_lock(self.db.get_bind(), 'offer-event:'+str(account_id)):
            prior = self.db.scalar(select(SyncLog).where(SyncLog.sync_type == EVENT,
                SyncLog.provider_account_id == account_id, SyncLog.sync_metadata['event_id'].astext == event_id))
            if prior:
                return {'status': 'duplicate'}
            self.db.add(SyncLog(provider='EBAY', provider_account_id=account_id, sync_type=EVENT,
                status=SyncLogStatus.PENDING, sync_metadata={'event_id': event_id, 'listing_id': str(item_id),
                    'offer_id': data.get('offerId'), 'verified_role': role}))
            self.db.commit()
        return {'status': 'queued'}
