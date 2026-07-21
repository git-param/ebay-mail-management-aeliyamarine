import asyncio
import logging
import time

from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.api.dependencies import get_current_user
from app.modules.search_sku.alreza_service import search_alreza
from app.modules.search_sku.atlaship_service import search_atlaship
from app.modules.search_sku.schemas import CrossPlatformSearchResponse, PlatformName, PlatformSearchResult
from app.modules.search_sku.zoho_service import search_zoho


logger = logging.getLogger(__name__)
router = APIRouter()


def _safe_error(platform: PlatformName, error: BaseException) -> str:
    message = str(error).strip()
    if message:
        return message
    return f'{platform.title()} search failed.'


def _platform_result(platform: PlatformName, result: object) -> PlatformSearchResult:
    if isinstance(result, BaseException):
        return PlatformSearchResult(platform=platform, success=False, count=0, error=_safe_error(platform, result))
    items = list(result)
    return PlatformSearchResult(platform=platform, success=True, count=len(items), items=items)


@router.get('/search-sku', response_model=CrossPlatformSearchResponse)
async def search_sku(
    q: str = Query(..., min_length=1),
    limit: int = Query(default=10, ge=1, le=50),
    current_user=Depends(get_current_user),
) -> CrossPlatformSearchResponse:
    """Search Zoho, Atlaship, and Alreza concurrently for authenticated users."""
    query = q.strip()
    if not query:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail='Search query must not be blank.')

    start = time.perf_counter()
    logger.info('Cross-platform search started query_length=%s limit=%s user_id=%s', len(query), limit, getattr(current_user, 'id', None))
    zoho_result, atlaship_result, alreza_result = await asyncio.gather(
        search_zoho(query, limit),
        search_atlaship(query, limit),
        search_alreza(query, limit),
        return_exceptions=True,
    )

    response = CrossPlatformSearchResponse(
        query=query,
        limit_per_platform=limit,
        zoho=_platform_result('zoho', zoho_result),
        atlaship=_platform_result('atlaship', atlaship_result),
        alreza=_platform_result('alreza', alreza_result),
    )
    duration_ms = round((time.perf_counter() - start) * 1000, 2)
    for platform in ('zoho', 'atlaship', 'alreza'):
        result = getattr(response, platform)
        logger.info(
            'Cross-platform search platform=%s query_length=%s limit=%s duration_ms=%s count=%s success=%s',
            platform,
            len(query),
            limit,
            duration_ms,
            result.count,
            result.success,
        )
    return response
