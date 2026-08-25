"""Provider-neutral message translation through a LibreTranslate-compatible API."""
from urllib.parse import urlparse

import requests

from app.core.config import get_settings


class TranslationService:
    def _translate_url(self, configured_url: str) -> str:
        base_url = configured_url.strip()
        if not base_url:
            raise RuntimeError('Translation is not configured. Set TRANSLATION_API_URL.')
        parsed = urlparse(base_url)
        if not parsed.scheme or not parsed.netloc:
            raise RuntimeError('TRANSLATION_API_URL must be an absolute URL.')
        return base_url.rstrip('/') if base_url.rstrip('/').endswith('/translate') else f'{base_url.rstrip("/")}/translate'

    def translate(self, text: str, target_language: str = 'en') -> dict:
        settings = get_settings()
        translate_url = self._translate_url(settings.translation_api_url)
        payload = {'q': text, 'source': 'auto', 'target': target_language, 'format': 'text'}
        api_key = settings.translation_api_key.strip()
        if api_key:
            payload['api_key'] = api_key
        response = requests.post(translate_url, json=payload, timeout=20)
        response.raise_for_status()
        data = response.json()
        translated = data.get('translatedText') or data.get('translated_text')
        if not translated:
            raise RuntimeError('Translation provider returned no translated text.')
        detected = data.get('detectedLanguage')
        if isinstance(detected, dict):
            detected = detected.get('language')
        return {'translated_text': translated, 'detected_language': detected}
