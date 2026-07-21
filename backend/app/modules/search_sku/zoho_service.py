import asyncio
import logging
from typing import Any

import requests

from app.core.config import get_settings
from app.modules.search_sku.schemas import PlatformProduct
from app.modules.search_sku.zoho_auth import ZohoAuthError, get_access_token, refresh_access_token


logger = logging.getLogger(__name__)

API_URL = 'https://www.zohoapis.in/inventory/v1'


class ZohoSearchError(RuntimeError):
    """Raised when Zoho inventory search fails."""


def _get_item_price(item: dict[str, Any]) -> Any:
    for field in ('cf_ebay_pricing_unformatted', 'cf_ebay_pricing', 'rate', 'sales_rate', 'purchase_rate'):
        value = item.get(field)
        if value not in (None, '', 0, 0.0):
            return value
    return ''


def _image_url(image_document_id: str | None, organization_id: str) -> str | None:
    if not image_document_id:
        return None
    return (
        f'https://inventory.zoho.in/DocTemplates_ItemImage_Small_{image_document_id}.zbfs'
        f'?organization_id={organization_id}'
    )


def normalize_zoho_item(item: dict[str, Any]) -> PlatformProduct:
    """Normalize a Zoho Inventory item into the unified product schema."""
    settings = get_settings()
    item_id = str(item.get('item_id') or '')
    image_document_id = str(item.get('image_document_id') or '').strip()
    metadata = {
        'brand': item.get('brand') or '',
        'condition': item.get('cf_condition') or '',
        'stock_on_hand': item.get('stock_on_hand', 0),
        'part_number': item.get('part_number') or '',
        'ebay_price': _get_item_price(item),
    }
    return PlatformProduct(
        platform='zoho',
        external_id=item_id or None,
        name=item.get('name') or item.get('sku') or 'Unnamed Zoho item',
        sku=item.get('sku') or None,
        image_url=_image_url(image_document_id, settings.zoho_organization_id),
        product_url=(
            f'https://inventory.zoho.in/app/{settings.zoho_organization_id}#/inventory/items/{item_id}'
            if item_id and settings.zoho_organization_id
            else 'https://inventory.zoho.in/app'
        ),
        metadata={key: value for key, value in metadata.items() if value not in (None, '')},
    )


def _zoho_get_items(query: str, limit: int) -> list[dict[str, Any]]:
    settings = get_settings()
    if not settings.zoho_organization_id:
        raise ZohoSearchError('Zoho organization ID is not configured.')

    params = {
        'organization_id': settings.zoho_organization_id,
        'search_text': query,
        'filter_by': 'Status.All',
        'page': 1,
        'per_page': limit,
        'sort_column': 'name',
        'sort_order': 'A',
    }

    def request_with_token(access_token: str) -> requests.Response:
        return requests.get(
            f'{API_URL}/items',
            headers={'Authorization': f'Zoho-oauthtoken {access_token}'},
            params=params,
            timeout=30,
        )

    try:
        response = request_with_token(get_access_token())
        if response.status_code == 401:
            response = request_with_token(refresh_access_token())
    except ZohoAuthError:
        raise
    except requests.Timeout as exc:
        raise ZohoSearchError('Zoho request timed out.') from exc
    except requests.RequestException as exc:
        raise ZohoSearchError('Zoho request failed.') from exc

    try:
        data = response.json()
    except ValueError as exc:
        raise ZohoSearchError('Zoho returned invalid JSON.') from exc

    if response.status_code != 200 or data.get('code') != 0:
        logger.error(
            'Zoho inventory search failed: status=%s response=%s',
            response.status_code,
            data,
        )

        raise ZohoSearchError(
            f"Zoho inventory search failed: "
            f"HTTP {response.status_code}, "
            f"code={data.get('code')}, "
            f"message={data.get('message') or data.get('error') or 'Unknown error'}"
        )

    items = data.get('items') or []
    if not isinstance(items, list):
        raise ZohoSearchError('Zoho inventory response was invalid.')
    return items


async def search_zoho(query: str, limit: int) -> list[PlatformProduct]:
    """Search Zoho Inventory items and return normalized products."""
    items = await asyncio.to_thread(_zoho_get_items, query, limit)
    deduped: list[PlatformProduct] = []
    seen_ids: set[str] = set()
    for item in items:
        if not isinstance(item, dict):
            continue
        product = normalize_zoho_item(item)
        key = product.external_id or product.product_url
        if key in seen_ids:
            continue
        seen_ids.add(key)
        deduped.append(product)
        if len(deduped) >= limit:
            break
    logger.info('Zoho search normalized %s products', len(deduped))
    return deduped
