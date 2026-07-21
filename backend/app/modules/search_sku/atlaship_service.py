import asyncio
import logging
import re
from typing import Any
from urllib.parse import quote_plus

import requests
from bs4 import BeautifulSoup

from app.modules.search_sku.schemas import PlatformProduct


logger = logging.getLogger(__name__)


class AtlashipSearchError(RuntimeError):
    """Raised when Atlaship search cannot be completed."""


class AtlasFeedExtractor:
    def __init__(self) -> None:
        self.blog_id = '4779734925367992915'
        self.feed_url = f'https://www.blogger.com/feeds/{self.blog_id}/posts/default'
        self.headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
        self.field_patterns = {
            'type_designation': [r'TYPE\s+DESIGNATION\s*[:：]\s*([A-Z0-9\s\-]+)', r'TYPE\s+DESIGNATION\s*[:：]\s*([^\n]+)'],
            'version': [r'VER\.?\s*[:：]?\s*([0-9\.]+)', r'VER\.?\s*[:：]?\s*([A-Z0-9\.]+)'],
            'serial_no': [r'SERIAL\.?NO\s*[:：]\s*([A-Z0-9/\-]+)', r'SERIAL\s+NUMBER\s*[:：]\s*([A-Z0-9/\-]+)', r'SN\s*[:：]\s*([A-Z0-9/\-]+)'],
            'date': [r'DATE\s*[:：]\s*([\d\-\.\/]+)'],
            'certificate': [r'CERTIFICATE\s*[:：]\s*([A-Z0-9&\-]+)'],
            'approved_by': [r'APPROVED\s+BY\s*[:：]\s*([A-Z0-9\s\(\)\-]+)'],
            'approved_for': [r'APPROVED\s+FOR\s*[:：]\s*([A-Z\s]+)'],
            'rated_voltage': [r'RATED\s+VOLTAGE\s*[:：]\s*([A-Z0-9\s]+)'],
            'rated_current': [r'RATED\s+CURRENT\s*[:：]\s*([A-Z0-9\.\s]+)'],
            'made_in': [r'MADE\s+IN\s*[:：]\s*([A-Z\s]+)'],
            'condition': [r'CONDITION\s*[:：]\s*([A-Z\s\/\-]+)'],
            'ref_no': [r'REF\.?NO\(S\)\s*[:：]?\s*([A-Z0-9/\.]+)', r'REF\.?NO\s*[:：]?\s*([A-Z0-9/\.]+)'],
            'mepc': [r'MEPC\s+([\d\(\)&]+)'],
            'certificate_no': [r'CERTIFICATE\s+NO\s*[:：]\s*([A-Z0-9\-]+)'],
        }

    def extract_image_from_html(self, html_content: str) -> str | None:
        soup = BeautifulSoup(html_content, 'html.parser')
        for image in soup.find_all('img'):
            src = image.get('src', '')
            if not src or 'icon' in src.lower() or 'avatar' in src.lower():
                continue
            if 'blogger.googleusercontent.com' in src:
                return re.sub(r'/s\d+(-c)?/', '/s1600/', src)
            if src.startswith('http') and any(ext in src.lower() for ext in ('.jpg', '.jpeg', '.png', '.gif', '.webp')):
                return src
        return None

    def extract_field_value(self, content: str, patterns: list[str]) -> str | None:
        for pattern in patterns:
            match = re.search(pattern, content, re.IGNORECASE | re.MULTILINE)
            if match:
                return re.sub(r'\s+', ' ', match.group(1)).strip()
        return None

    def extract_from_entry(self, entry: dict[str, Any]) -> dict[str, Any] | None:
        content = entry.get('content', {}).get('$t', '')
        title = entry.get('title', {}).get('$t', '')
        published = entry.get('published', {}).get('$t', '')
        url = next((link.get('href') for link in entry.get('link', []) if link.get('rel') == 'alternate'), None)
        extracted = {'title': title, 'url': url, 'published': published, 'image_url': self.extract_image_from_html(content), 'data': {}}

        for field, patterns in self.field_patterns.items():
            value = self.extract_field_value(content, patterns)
            if value:
                extracted['data'][field] = value

        if not extracted['data'].get('serial_no'):
            serial_match = re.search(r'(?:SERIAL|SN)[\s:]+([A-Z0-9/\-]+)', title, re.IGNORECASE)
            if serial_match:
                extracted['data']['serial_no'] = serial_match.group(1)
        if not extracted['data'].get('ref_no'):
            ref_match = re.search(r'REF[\s:]+([A-Z0-9/\.]+)', title, re.IGNORECASE)
            if ref_match:
                extracted['data']['ref_no'] = ref_match.group(1)
        return extracted if (url and (extracted['data'] or extracted['image_url'])) else None

    def search_posts(self, query: str, limit: int) -> list[dict[str, Any]]:
        try:
            response = requests.get(
                f'{self.feed_url}?q={quote_plus(query)}&v=2&alt=json',
                headers=self.headers,
                timeout=15,
            )
            response.raise_for_status()
            data = response.json()
        except requests.Timeout as exc:
            raise AtlashipSearchError('Atlaship search timed out.') from exc
        except requests.RequestException as exc:
            raise AtlashipSearchError('Atlaship feed request failed.') from exc
        except ValueError as exc:
            raise AtlashipSearchError('Atlaship feed returned invalid JSON.') from exc

        entries = data.get('feed', {}).get('entry', [])
        results = []
        for entry in entries if isinstance(entries, list) else []:
            try:
                extracted = self.extract_from_entry(entry)
            except Exception as exc:
                logger.warning('Skipping malformed Atlaship feed entry: %s', exc)
                continue
            if extracted:
                results.append(extracted)
            if len(results) >= limit:
                break
        return results


def _normalize(raw: dict[str, Any]) -> PlatformProduct:
    data = raw.get('data') or {}
    sku = data.get('ref_no') or data.get('serial_no') or data.get('type_designation') or data.get('model') or None
    return PlatformProduct(
        platform='atlaship',
        external_id=raw.get('url'),
        name=raw.get('title') or 'Untitled Atlaship product',
        sku=sku,
        image_url=raw.get('image_url'),
        product_url=raw.get('url'),
        metadata={**data, 'published': raw.get('published') or ''},
    )


async def search_atlaship(query: str, limit: int) -> list[PlatformProduct]:
    """Search Atlaship Blogger feed and return normalized products."""
    raw_results = await asyncio.to_thread(AtlasFeedExtractor().search_posts, query, limit)
    products: list[PlatformProduct] = []
    seen_urls: set[str] = set()
    for raw in raw_results:
        product = _normalize(raw)
        if product.product_url in seen_urls:
            continue
        seen_urls.add(product.product_url)
        products.append(product)
    return products
