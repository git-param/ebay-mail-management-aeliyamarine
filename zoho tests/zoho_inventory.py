import json
import os
import time

import requests


CLIENT_ID = os.getenv("ZOHO_CLIENT_ID", "1000.Y06ENWZQ8EM6L5S6WBZNH6HGK75D4Y")
CLIENT_SECRET = os.getenv("ZOHO_CLIENT_SECRET", "b234404bf7090f3b94adcf779f4adcaa9453b881b8")
ORGANIZATION_ID = os.getenv(
    "ZOHO_ORGANIZATION_ID",
    "60001240355",
)

ACCOUNTS_URL = "https://accounts.zoho.in"
API_URL = "https://www.zohoapis.in/inventory/v1"
TOKEN_FILE = "zoho_tokens.json"


def load_tokens():
    if not os.path.exists(TOKEN_FILE):
        raise RuntimeError(
            "zoho_tokens.json was not found. Run final_token_getter.py once."
        )

    with open(TOKEN_FILE, "r", encoding="utf-8") as file:
        return json.load(file)


def save_tokens(tokens):
    with open(TOKEN_FILE, "w", encoding="utf-8") as file:
        json.dump(tokens, file, indent=2)


def get_item_price(item):
    """
    Return the eBay USD custom price when available.
    Falls back to other Zoho price fields.
    """

    possible_fields = [
        "cf_ebay_pricing_unformatted",
        "cf_ebay_pricing",
        "rate",
        "sales_rate",
        "purchase_rate",
    ]

    for field in possible_fields:
        value = item.get(field)

        if value not in (None, "", 0, 0.0):
            return value

    return ""

def serialize_item(item):
    item_id = str(item.get("item_id", ""))

    return {
        "item_id": item_id,
        "name": item.get("name", ""),
        "sku": item.get("sku", ""),
        "brand": item.get("brand", ""),
        "part_number": item.get("part_number", ""),
        "condition": item.get("cf_condition", ""),
        "stock_on_hand": item.get("stock_on_hand", 0),
        "ebay_price": get_item_price(item),
        "has_image": bool(
            item.get("image_document_id")
            or item.get("has_attachment")
            or item.get("image_name")
        ),
        "image_url": (
            f"/api/items/{item_id}/image"
            if item_id
            else None
        ),
        "zoho_url": (
            "https://inventory.zoho.in/app/60001240355"
            f"#/inventory/items/{item_id}"
            if item_id
            else None
        ),
    }

def refresh_access_token():
    tokens = load_tokens()

    refresh_token = tokens.get("refresh_token")

    if not refresh_token:
        raise RuntimeError(
            "Refresh token is missing. Run final_token_getter.py again."
        )

    response = requests.post(
        f"{ACCOUNTS_URL}/oauth/v2/token",
        data={
            "refresh_token": refresh_token,
            "client_id": CLIENT_ID,
            "client_secret": CLIENT_SECRET,
            "grant_type": "refresh_token",
        },
        timeout=30,
    )

    data = response.json()

    if response.status_code != 200 or "access_token" not in data:
        raise RuntimeError(
            f"Could not refresh access token: {json.dumps(data, indent=2)}"
        )

    tokens["access_token"] = data["access_token"]
    tokens["expires_in"] = data.get("expires_in", 3600)
    tokens["created_at"] = int(time.time())

    save_tokens(tokens)

    return tokens["access_token"]


def get_access_token():
    tokens = load_tokens()

    access_token = tokens.get("access_token")
    created_at = tokens.get("created_at", 0)
    expires_in = tokens.get("expires_in", 3600)

    token_expired = (
        not access_token
        or int(time.time()) >= created_at + expires_in - 120
    )

    if token_expired:
        return refresh_access_token()

    return access_token


def zoho_get(endpoint, params):
    access_token = get_access_token()

    response = requests.get(
        f"{API_URL}/{endpoint.lstrip('/')}",
        headers={
            "Authorization": f"Zoho-oauthtoken {access_token}",
        },
        params=params,
        timeout=60,
    )

    if response.status_code == 401:
        access_token = refresh_access_token()

        response = requests.get(
            f"{API_URL}/{endpoint.lstrip('/')}",
            headers={
                "Authorization": f"Zoho-oauthtoken {access_token}",
            },
            params=params,
            timeout=60,
        )

    try:
        data = response.json()
    except ValueError:
        raise RuntimeError(
            f"Zoho returned invalid JSON: {response.text[:500]}"
        )

    if response.status_code != 200 or data.get("code") != 0:
        raise RuntimeError(
            f"Zoho API error: {json.dumps(data, indent=2)}"
        )

    return data

def get_item_image(item_id):
    access_token = get_access_token()

    url = f"{API_URL}/items/{item_id}/image"

    response = requests.get(
        url,
        headers={
            "Authorization": f"Zoho-oauthtoken {access_token}",
        },
        params={
            "organization_id": ORGANIZATION_ID,
        },
        timeout=60,
    )

    if response.status_code == 401:
        access_token = refresh_access_token()

        response = requests.get(
            url,
            headers={
                "Authorization": (
                    f"Zoho-oauthtoken {access_token}"
                ),
            },
            params={
                "organization_id": ORGANIZATION_ID,
            },
            timeout=60,
        )

    if response.status_code != 200:
        raise RuntimeError(
            f"Image request failed for {item_id}: "
            f"{response.status_code} {response.text[:300]}"
        )

    return {
        "content": response.content,
        "content_type": response.headers.get(
            "Content-Type",
            "image/jpeg",
        ),
    }

def search_exact_sku(keyword):
    results = search_inventory(keyword, limit=50)

    exact_results = [
        item
        for item in results
        if str(item.get("sku", "")).strip().lower()
        == keyword.strip().lower()
    ]

    return exact_results

def search_inventory(keyword, limit=20):
    keyword = str(keyword).strip()

    if not keyword:
        return []

    limit = max(1, min(int(limit), 200))
    query = keyword.casefold()

    results = []
    seen_item_ids = set()

    def matches(item):
        searchable_values = [
            item.get("name"),
            item.get("item_name"),
            item.get("sku"),
            item.get("brand"),
            item.get("manufacturer"),
            item.get("part_number"),
            item.get("cf_condition"),
            item.get("description"),
            item.get("purchase_description"),
        ]

        for value in searchable_values:
            if query in str(value or "").casefold():
                return True

        # Search every custom field returned by Zoho.
        for key, value in item.items():
            if key.startswith("cf_"):
                if query in str(value or "").casefold():
                    return True

        return False

    def add_matching_items(items):
        for item in items:
            item_id = str(item.get("item_id", ""))

            if not item_id or item_id in seen_item_ids:
                continue

            if matches(item):
                results.append(item)
                seen_item_ids.add(item_id)

            if len(results) >= limit:
                return True

        return False

    # First use Zoho's normal search.
    search_data = zoho_get(
        "items",
        {
            "organization_id": ORGANIZATION_ID,
            "search_text": keyword,
            "filter_by": "Status.All",
            "page": 1,
            "per_page": 200,
        },
    )

    if add_matching_items(search_data.get("items", [])):
        return results[:limit]

    # If Zoho search does not find enough results, scan the inventory
    # in Zoho's original name-based order.
    page = 1

    while True:
        data = zoho_get(
            "items",
            {
                "organization_id": ORGANIZATION_ID,
                "filter_by": "Status.All",
                "sort_column": "name",
                "sort_order": "A",
                "page": page,
                "per_page": 200,
            },
        )

        if add_matching_items(data.get("items", [])):
            break

        page_context = data.get("page_context", {})

        if not page_context.get("has_more_page"):
            break

        page += 1

    return results[:limit]