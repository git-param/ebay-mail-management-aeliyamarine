"""Combine listing previews without letting empty provider fields erase cached data."""


def merge_listing_metadata(*sources):
    listing, images = {}, []
    for source in sources:
        for key, value in (source or {}).items():
            if value is not None and (not isinstance(value, str) or value.strip()):
                listing[key] = value
        candidates = [(source or {}).get('image_url'), *((source or {}).get('image_urls') or [])]
        images.extend(value.strip() for value in candidates if isinstance(value, str) and value.strip())
    if images:
        listing['image_urls'] = list(dict.fromkeys([listing.get('image_url'), *images]))
    return listing
