"""Provider-neutral message translation through a LibreTranslate-compatible API."""

from urllib.parse import urlparse

import requests

from app.core.config import get_settings


class TranslationService:
    """
    Translate conversation messages through one or more
    LibreTranslate-compatible providers.

    Important:
    Source-language detection is intentionally delegated to the
    translation provider using ``source='auto'``.

    Do not try to infer English based on ASCII characters here.
    Languages such as German, Dutch, French, Spanish and Italian
    frequently contain mostly ASCII characters as well.
    """

    def _translate_url(
        self,
        configured_url: str,
    ) -> str:
        base_url = configured_url.strip()

        if not base_url:
            raise RuntimeError(
                'Translation is not configured. '
                'Set TRANSLATION_API_URL.'
            )

        parsed = urlparse(base_url)

        if (
            not parsed.scheme
            or not parsed.netloc
        ):
            raise RuntimeError(
                'TRANSLATION_API_URL must be '
                'an absolute URL.'
            )

        normalized_url = (
            base_url.rstrip('/')
        )

        if normalized_url.endswith(
            '/translate'
        ):
            return normalized_url

        return (
            f'{normalized_url}/translate'
        )

    def translate(
        self,
        text: str,
        target_language: str = 'en',
    ) -> dict:
        """
        Translate a message into the requested language.

        The provider performs automatic source-language detection.

        This is deliberately preferred over local heuristics because
        checking whether characters are ASCII cannot reliably determine
        whether text is English.
        """

        normalized_text = str(
            text or ''
        ).strip()

        if not normalized_text:
            raise ValueError(
                'Text is required for translation.'
            )

        normalized_target = str(
            target_language or 'en'
        ).strip().lower()

        if not normalized_target:
            normalized_target = 'en'

        settings = get_settings()

        payload = {
            'q': normalized_text,
            'source': 'auto',
            'target': normalized_target,
            'format': 'text',
        }

        api_key = (
            settings
            .translation_api_key
            .strip()
        )

        if api_key:
            payload['api_key'] = api_key

        errors = []

        for configured_url in (
            settings.translation_urls
        ):
            try:
                translate_url = (
                    self._translate_url(
                        configured_url
                    )
                )
            except RuntimeError as exc:
                errors.append(str(exc))
                continue

            try:
                response = requests.post(
                    translate_url,
                    json=payload,
                    timeout=20,
                )

                response.raise_for_status()

                data = response.json()

            except requests.HTTPError as exc:
                errors.append(
                    self._provider_error(
                        translate_url,
                        exc.response,
                    )
                )
                continue

            except requests.RequestException as exc:
                errors.append(
                    f'{translate_url}: {exc}'
                )
                continue

            except ValueError:
                # response.json() raises ValueError when the
                # provider returns HTML or another invalid payload.
                errors.append(
                    f'{translate_url}: '
                    'provider returned invalid JSON'
                )
                continue

            translated = (
                data.get(
                    'translatedText'
                )
                or data.get(
                    'translated_text'
                )
            )

            if not translated:
                errors.append(
                    f'{translate_url}: '
                    'provider returned no '
                    'translated text'
                )
                continue

            detected = (
                data.get(
                    'detectedLanguage'
                )
                or data.get(
                    'detected_language'
                )
            )

            if isinstance(
                detected,
                dict,
            ):
                detected = (
                    detected.get(
                        'language'
                    )
                    or detected.get(
                        'code'
                    )
                )

            return {
                'translated_text': (
                    translated
                ),
                'detected_language': (
                    detected
                ),
            }

        detail = (
            errors[-1]
            if errors
            else (
                'No translation providers '
                'were configured.'
            )
        )

        raise RuntimeError(
            f'Translation failed. {detail}'
        )

    def _provider_error(
        self,
        translate_url: str,
        response,
    ) -> str:
        if response is None:
            return (
                f'{translate_url}: '
                'provider rejected '
                'the request'
            )

        body = (
            response.text or ''
        ).strip()

        if len(body) > 200:
            body = (
                f'{body[:200]}...'
            )

        return (
            f'{translate_url}: '
            f'HTTP '
            f'{response.status_code} '
            f'{body}'
        ).strip()