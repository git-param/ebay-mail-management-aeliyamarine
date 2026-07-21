from typing import Any, Literal

from pydantic import BaseModel, Field


PlatformName = Literal['zoho', 'atlaship', 'alreza']


class PlatformProduct(BaseModel):
    platform: PlatformName
    external_id: str | None = None
    name: str
    sku: str | None = None
    image_url: str | None = None
    product_url: str
    metadata: dict[str, Any] = Field(default_factory=dict)


class PlatformSearchResult(BaseModel):
    platform: PlatformName
    success: bool
    count: int
    items: list[PlatformProduct] = Field(default_factory=list)
    error: str | None = None


class CrossPlatformSearchResponse(BaseModel):
    query: str
    limit_per_platform: int
    zoho: PlatformSearchResult
    atlaship: PlatformSearchResult
    alreza: PlatformSearchResult
