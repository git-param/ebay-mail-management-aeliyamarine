import json
import logging
import threading
import time
from pathlib import Path
from typing import Any

import requests

from app.core.config import get_settings


logger = logging.getLogger(__name__)

ACCOUNTS_URL = 'https://accounts.zoho.in'
TOKEN_EXPIRY_SKEW_SECONDS = 120
_refresh_lock = threading.Lock()


class ZohoAuthError(RuntimeError):
    """Raised when Zoho OAuth credentials or token state are invalid."""


def _token_file_path() -> Path:
    settings = get_settings()
    token_file = Path(settings.zoho_token_file)
    if token_file.is_absolute():
        return token_file
    return Path(__file__).resolve().parents[4] / token_file


def _require_zoho_credentials() -> tuple[str, str]:
    settings = get_settings()
    if not settings.zoho_client_id or not settings.zoho_client_secret:
        raise ZohoAuthError('Zoho authentication is not configured.')
    return settings.zoho_client_id, settings.zoho_client_secret


def load_tokens() -> dict[str, Any]:
    """Load persisted Zoho OAuth token data from the configured token file."""
    token_path = _token_file_path()
    if not token_path.exists():
        raise ZohoAuthError('Zoho token file was not found.')

    try:
        with token_path.open('r', encoding='utf-8') as token_file:
            tokens = json.load(token_file)
    except (OSError, json.JSONDecodeError) as exc:
        raise ZohoAuthError('Zoho token file could not be read.') from exc

    if not isinstance(tokens, dict):
        raise ZohoAuthError('Zoho token file is invalid.')
    if not tokens.get('refresh_token'):
        raise ZohoAuthError('Zoho refresh token is missing.')
    return tokens


def save_tokens(tokens: dict[str, Any]) -> None:
    """Persist refreshed Zoho OAuth token data."""
    token_path = _token_file_path()
    try:
        token_path.parent.mkdir(parents=True, exist_ok=True)
        with token_path.open('w', encoding='utf-8') as token_file:
            json.dump(tokens, token_file, indent=2)
    except OSError as exc:
        raise ZohoAuthError('Zoho token file could not be updated.') from exc


def _is_access_token_expired(tokens: dict[str, Any]) -> bool:
    access_token = tokens.get('access_token')
    created_at = int(tokens.get('created_at') or 0)
    expires_in = int(tokens.get('expires_in') or 3600)
    return not access_token or int(time.time()) >= created_at + expires_in - TOKEN_EXPIRY_SKEW_SECONDS


def refresh_access_token() -> str:
    """Refresh the Zoho access token using the saved refresh token."""
    client_id, client_secret = _require_zoho_credentials()
    tokens = load_tokens()

    try:
        response = requests.post(
            f'{ACCOUNTS_URL}/oauth/v2/token',
            data={
                'refresh_token': tokens['refresh_token'],
                'client_id': client_id,
                'client_secret': client_secret,
                'grant_type': 'refresh_token',
            },
            timeout=30,
        )
    except requests.Timeout as exc:
        raise ZohoAuthError('Zoho authentication timed out.') from exc
    except requests.RequestException as exc:
        raise ZohoAuthError('Zoho authentication request failed.') from exc

    try:
        data = response.json()
    except ValueError as exc:
        raise ZohoAuthError('Zoho authentication returned invalid JSON.') from exc

    if response.status_code != 200 or 'access_token' not in data:
        error = str(data.get('error') or data.get('message') or '').lower()
        if 'invalid_client' in error:
            raise ZohoAuthError('Zoho client credentials are invalid.')
        if 'invalid_code' in error or 'invalid_token' in error:
            raise ZohoAuthError('Zoho refresh token is invalid.')
        raise ZohoAuthError('Zoho authentication failed.')

    tokens['access_token'] = data['access_token']
    tokens['expires_in'] = data.get('expires_in', 3600)
    tokens['created_at'] = int(time.time())
    save_tokens(tokens)
    logger.info('Zoho access token refreshed')
    return str(tokens['access_token'])


def get_access_token() -> str:
    """Return a valid Zoho access token, refreshing it when required."""
    tokens = load_tokens()
    if not _is_access_token_expired(tokens):
        return str(tokens['access_token'])

    with _refresh_lock:
        tokens = load_tokens()
        if not _is_access_token_expired(tokens):
            return str(tokens['access_token'])
        return refresh_access_token()
