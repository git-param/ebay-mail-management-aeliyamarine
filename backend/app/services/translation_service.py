"""Provider-neutral message translation through a LibreTranslate-compatible API."""
import requests

from app.core.config import get_settings


class TranslationService:
    def translate(self, text: str, target_language: str = 'en') -> dict:
        settings = get_settings()
        if not settings.translation_api_url:
            raise RuntimeError('Translation is not configured. Set TRANSLATION_API_URL.')
        payload = {'q': text, 'source': 'auto', 'target': target_language, 'format': 'text'}
        if settings.translation_api_key:
            payload['api_key'] = settings.translation_api_key
        response = requests.post(settings.translation_api_url, json=payload, timeout=20)
        response.raise_for_status()
        data = response.json()
        translated = data.get('translatedText') or data.get('translated_text')
        if not translated:
            raise RuntimeError('Translation provider returned no translated text.')
        detected = data.get('detectedLanguage')
        if isinstance(detected, dict):
            detected = detected.get('language')
        return {'translated_text': translated, 'detected_language': detected}
