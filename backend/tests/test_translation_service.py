from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.api.v1.routes.conversations import visible_conversation_offers
from app.services.translation_service import TranslationService


def test_translate_uses_libretranslate_without_api_key(monkeypatch):
    post_calls = []

    monkeypatch.setattr(
        'app.services.translation_service.get_settings',
        lambda: SimpleNamespace(
            translation_api_url='https://libretranslate.com/',
            translation_api_key='',
        ),
    )

    def fake_post(url, json, timeout):
        post_calls.append({'url': url, 'json': json, 'timeout': timeout})
        return SimpleNamespace(
            raise_for_status=lambda: None,
            json=lambda: {'translatedText': 'Hola', 'detectedLanguage': {'language': 'en'}},
        )

    monkeypatch.setattr('app.services.translation_service.requests.post', fake_post)

    result = TranslationService().translate('Hello', 'es')

    assert result == {'translated_text': 'Hola', 'detected_language': 'en'}
    assert post_calls == [
        {
            'url': 'https://libretranslate.com/translate',
            'json': {'q': 'Hello', 'source': 'auto', 'target': 'es', 'format': 'text'},
            'timeout': 20,
        }
    ]


def test_translate_accepts_configured_translate_endpoint(monkeypatch):
    post_calls = []

    monkeypatch.setattr(
        'app.services.translation_service.get_settings',
        lambda: SimpleNamespace(
            translation_api_url='https://libretranslate.com/translate',
            translation_api_key=' optional-key ',
        ),
    )

    def fake_post(url, json, timeout):
        post_calls.append({'url': url, 'json': json, 'timeout': timeout})
        return SimpleNamespace(
            raise_for_status=lambda: None,
            json=lambda: {'translated_text': 'Bonjour', 'detectedLanguage': 'fr'},
        )

    monkeypatch.setattr('app.services.translation_service.requests.post', fake_post)

    result = TranslationService().translate('Hello', 'fr')

    assert result == {'translated_text': 'Bonjour', 'detected_language': 'fr'}
    assert post_calls[0]['url'] == 'https://libretranslate.com/translate'
    assert post_calls[0]['json']['api_key'] == 'optional-key'


def test_translate_rejects_relative_translation_url(monkeypatch):
    monkeypatch.setattr(
        'app.services.translation_service.get_settings',
        lambda: SimpleNamespace(translation_api_url='/translate', translation_api_key=''),
    )

    with pytest.raises(RuntimeError, match='absolute URL'):
        TranslationService().translate('Hello', 'es')


def test_visible_conversation_offers_keeps_one_accepted_event():
    first_accepted = SimpleNamespace(
        id=uuid4(),
        status='ACCEPTED',
        listing_id='334411432344',
        buyer_username='n_ma067',
        created_at_provider='2026-08-16T08:52:00+00:00',
        created_at='2026-08-16T08:52:00+00:00',
    )
    latest_accepted = SimpleNamespace(
        id=uuid4(),
        status='ACCEPTED',
        listing_id='334411432344',
        buyer_username='n_ma067',
        created_at_provider='2026-08-17T10:58:00+00:00',
        created_at='2026-08-17T10:58:00+00:00',
    )
    sent_counteroffer = SimpleNamespace(
        id=uuid4(),
        status='PENDING',
        listing_id='334411432344',
        buyer_username='n_ma067',
        created_at_provider='2026-08-16T08:54:00+00:00',
        created_at='2026-08-16T08:54:00+00:00',
    )

    visible = visible_conversation_offers(
        [first_accepted, sent_counteroffer, latest_accepted]
    )

    assert visible == [sent_counteroffer, latest_accepted]
