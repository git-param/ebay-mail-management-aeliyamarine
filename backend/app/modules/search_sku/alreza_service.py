import asyncio
import logging
import re
from typing import Any
from urllib.parse import quote_plus, urljoin

import requests
from bs4 import BeautifulSoup

from app.modules.search_sku.schemas import PlatformProduct


logger = logging.getLogger(__name__)


class AlrezaSearchError(RuntimeError):
    """Raised when Alreza search cannot be completed."""


class AlRezaExtractor:
    def __init__(self) -> None:
        self.base_url = 'https://www.alrezaenterprise.com'
        self.headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
        self.patterns = {
            'brand': [r'BRAND\s*[:：]\s*([A-Z0-9\-]+)'],
            'model': [r'MODEL\s*[:：]\s*([A-Z0-9\-]+)'],
            'type': [r'TYPE\s*[:：]\s*([A-Z0-9\s\-]+)'],
            'rating': [r'RATING\s*[:：]\s*([A-Z0-9\s\/]+)'],
            'input_voltage': [r'(?:INPUT\s*)?VOLTAGE\s*[:：]\s*([A-Z0-9\/\s]+)'],
            'frequency': [r'FREQUENCY\s*[:：]\s*([A-Z0-9\s]+)'],
            'control_input': [r'CONTROL\s*INPUT\s*[:：]\s*([A-Z0-9\-]+)'],
            'power_device': [r'POWER\s*DEVICE\s*[:：]\s*([A-Z0-9\s\(\)]+)'],
            'phase': [r'PHASE\s*[:：]\s*([A-Z0-9]+)'],
            'application': [r'APPLICATION\s*[:：]\s*([A-Z0-9\s,]+)'],
            'condition': [r'CONDITION\s*[:：]\s*([A-Z0-9\s\/\-]+)'],
            'qty': [r'QTY\s*[:：]\s*([A-Z0-9]+)'],
            'ref': [r'REF\s*[:：]?\s*([A-Z0-9\/\.]+)'],
        }

    def search_blog(self, query: str, limit: int) -> list[dict[str, str]]:
        try:
            response = requests.get(f'{self.base_url}/search?q={quote_plus(query)}', headers=self.headers, timeout=15)
            response.raise_for_status()
        except requests.Timeout as exc:
            raise AlrezaSearchError('Alreza search timed out.') from exc
        except requests.RequestException as exc:
            raise AlrezaSearchError('Alreza search page could not be loaded.') from exc

        soup = BeautifulSoup(response.content, 'html.parser')
        post_links: list[dict[str, str]] = []
        for title_element in soup.find_all(['h1', 'h2', 'h3']):
            link = title_element.find('a')
            href = link.get('href') if link else ''
            if href and '/202' in href and '/search' not in href:
                post_links.append({'title': link.get_text(strip=True), 'url': urljoin(self.base_url, href)})
        for link in soup.find_all('a'):
            href = link.get('href', '')
            if '/202' in href:
                post_links.append({'title': link.get_text(strip=True) or 'Blog Post', 'url': urljoin(self.base_url, href)})

        unique_links = []
        seen_urls: set[str] = set()
        for post in post_links:
            if post['url'] in seen_urls:
                continue
            seen_urls.add(post['url'])
            unique_links.append(post)
            if len(unique_links) >= limit:
                break
        return unique_links

    def extract_first_image(self, soup: BeautifulSoup) -> str | None:
        for image in soup.find_all('img'):
            src = image.get('src', '')
            if not src or 'icon' in src.lower() or 'avatar' in src.lower():
                continue
            if 's72-c' in src:
                src = re.sub(r's\d+(-c)?', 's1600', src)
            if src.startswith('http'):
                return src
        content = soup.find('div', {'class': 'post-body'}) or soup.find('div', {'class': 'entry-content'})
        image = content.find('img') if content else None
        src = image.get('src', '') if image else ''
        return src if src.startswith('http') else None

    def extract_from_post(self, post_data: dict[str, str]) -> dict[str, Any] | None:
        try:
            response = requests.get(post_data['url'], headers=self.headers, timeout=15)
            response.raise_for_status()
        except requests.Timeout as exc:
            raise AlrezaSearchError('Alreza detail page timed out.') from exc
        except requests.RequestException as exc:
            logger.warning('Skipping Alreza detail page: %s', exc)
            return None

        soup = BeautifulSoup(response.content, 'html.parser')
        text = soup.get_text(separator=' ', strip=True)
        extracted = {'title': post_data['title'], 'url': post_data['url'], 'image_url': self.extract_first_image(soup), 'data': {}}
        for field, pattern_list in self.patterns.items():
            for pattern in pattern_list:
                match = re.search(pattern, text, re.IGNORECASE)
                if match:
                    extracted['data'][field] = match.group(1).strip()
                    break
        if not extracted['data'].get('model'):
            model_match = re.search(r'(TPR-\w+)', post_data['title'], re.IGNORECASE)
            if model_match:
                extracted['data']['model'] = model_match.group(1)
        if not extracted['data'].get('rating'):
            rating_match = re.search(r'(\d+)\s*A', post_data['title'], re.IGNORECASE)
            if rating_match:
                extracted['data']['rating'] = f'{rating_match.group(1)}A'
        if not extracted['data'].get('input_voltage'):
            voltage_match = re.search(r'(AC\s*\d+/\d+V|\d+V)', post_data['title'], re.IGNORECASE)
            if voltage_match:
                extracted['data']['input_voltage'] = voltage_match.group(1)
        return extracted if extracted['data'] or extracted['image_url'] else None

    def search_and_extract(self, query: str, limit: int) -> list[dict[str, Any]]:
        results = []
        for post in self.search_blog(query, limit):
            extracted = self.extract_from_post(post)
            if extracted:
                results.append(extracted)
            if len(results) >= limit:
                break
        return results


def _normalize(raw: dict[str, Any]) -> PlatformProduct:
    data = raw.get('data') or {}
    return PlatformProduct(
        platform='alreza',
        external_id=raw.get('url'),
        name=raw.get('title') or 'Untitled Alreza product',
        sku=data.get('ref') or data.get('model') or None,
        image_url=raw.get('image_url'),
        product_url=raw.get('url'),
        metadata=data,
    )


async def search_alreza(query: str, limit: int) -> list[PlatformProduct]:
    """Search Alreza blog pages and return normalized products."""
    raw_results = await asyncio.to_thread(AlRezaExtractor().search_and_extract, query, limit)
    products: list[PlatformProduct] = []
    seen_urls: set[str] = set()
    for raw in raw_results:
        product = _normalize(raw)
        if product.product_url in seen_urls:
            continue
        seen_urls.add(product.product_url)
        products.append(product)
    return products
