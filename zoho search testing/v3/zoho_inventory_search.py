import json
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, quote, urlparse

import requests

APP_VERSION = "ZOHO-INVENTORY-SEARCH-v4"
BASE_URL = "https://apex.200.141.3.14.sslip.io"
REQUEST_TIMEOUT = 30
HOST = "127.0.0.1"
PORT = 5000

HERE = Path(__file__).resolve().parent
HTML_PATH = HERE / "zoho_inventory_search.html"
ENV_PATH = HERE / ".env"


def load_local_env() -> None:
    if not ENV_PATH.exists():
        return
    for raw_line in ENV_PATH.read_text(encoding="utf-8-sig").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ[key.strip()] = value.strip().strip('"').strip("'")


def get_api_key() -> str:
    load_local_env()
    return (os.getenv("ZOHO_LOOKUP_API_KEY") or "").strip()


def headers() -> dict[str, str]:
    key = get_api_key()
    if not key:
        raise RuntimeError("ZOHO_LOOKUP_API_KEY is missing from .env")
    return {"X-API-Key": key, "Accept": "application/json"}


def upstream_get(path: str, params: dict[str, Any] | None = None) -> tuple[int, Any]:
    try:
        r = requests.get(
            f"{BASE_URL}{path}",
            headers=headers(),
            params=params,
            timeout=REQUEST_TIMEOUT,
        )
    except RuntimeError as exc:
        return 500, {"error": str(exc)}
    except requests.Timeout:
        return 504, {"error": "Apex API request timed out."}
    except requests.RequestException as exc:
        return 502, {"error": "Could not reach Apex API.", "details": str(exc)}

    try:
        data = r.json()
    except ValueError:
        return 502, {
            "error": "Apex API returned non-JSON.",
            "upstream_status": r.status_code,
            "details": r.text[:2000],
        }

    if not r.ok:
        msg = "Apex API returned an error."
        if isinstance(data, dict):
            msg = data.get("message") or data.get("error") or data.get("detail") or msg
        return r.status_code, {"error": msg, "details": data}

    return 200, data


def extract_items(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        return [x for x in payload if isinstance(x, dict)]

    if not isinstance(payload, dict):
        return []

    for key in ("items", "results", "records"):
        value = payload.get(key)
        if isinstance(value, list):
            return [x for x in value if isinstance(x, dict)]

    data = payload.get("data")
    if isinstance(data, list):
        return [x for x in data if isinstance(x, dict)]

    if isinstance(data, dict):
        for key in ("items", "results", "records"):
            value = data.get(key)
            if isinstance(value, list):
                return [x for x in value if isinstance(x, dict)]

    return []


def extract_pagination(payload: Any, page: int, per_page: int, count: int) -> dict[str, Any]:
    out = {"page": page, "per_page": per_page, "count": count}

    if not isinstance(payload, dict):
        out["has_more"] = count >= per_page
        return out

    candidates = [payload]
    for key in ("pagination", "page_context", "meta"):
        if isinstance(payload.get(key), dict):
            candidates.append(payload[key])

    aliases = {
        "page": ("page", "current_page"),
        "per_page": ("per_page", "page_size", "limit"),
        "total": ("total", "total_count", "total_items"),
        "total_pages": ("total_pages", "pages", "page_count", "last_page"),
        "has_more": ("has_more", "has_more_page", "more_records"),
    }

    for dest, names in aliases.items():
        for src in candidates:
            hit = False
            for name in names:
                if name in src and src[name] is not None:
                    out[dest] = src[name]
                    hit = True
                    break
            if hit:
                break

    if "has_more" not in out:
        if out.get("total_pages") is not None:
            out["has_more"] = int(out.get("page", page)) < int(out["total_pages"])
        elif out.get("total") is not None:
            out["has_more"] = (
                int(out.get("page", page)) * int(out.get("per_page", per_page))
                < int(out["total"])
            )
        else:
            out["has_more"] = count >= per_page

    return out


SEARCH_FIELDS = (
    "sku",
    "item_name",
    "name",
    "brand",
    "manufacturer",
    "mpn",
    "condition",
    "description",
    "zoho_item_id",
)


def item_matches(item: dict[str, Any], query: str) -> bool:
    q = query.strip().lower()
    if not q:
        return True

    for field in SEARCH_FIELDS:
        value = item.get(field)
        if value is not None and q in str(value).lower():
            return True
    return False


def fetch_page(page: int, per_page: int, search_param: str | None = None, query: str = ""):
    params: dict[str, Any] = {"page": page, "per_page": per_page}
    if search_param and query:
        params[search_param] = query
    return upstream_get("/api/zoho/items", params=params)


def search_items(query: str, page: int, per_page: int) -> tuple[int, dict[str, Any]]:
    """
    Try common upstream search parameter names. We only accept an upstream
    result set if the returned rows actually match the user's query.

    If the custom Apex list endpoint ignores all search parameters, we do NOT
    display unrelated rows. Instead, we return a clear message explaining that
    global text search is unsupported by the current endpoint.
    """
    query = query.strip()
    page = max(1, page)
    per_page = min(max(1, per_page), 200)

    if not query:
        status, payload = fetch_page(page, per_page)
        if status != 200:
            return status, {"success": False, **payload}
        items = extract_items(payload)
        return 200, {
            "success": True,
            "mode": "browse",
            "query": "",
            "items": items,
            "pagination": extract_pagination(payload, page, per_page, len(items)),
        }

    # Try common parameter names one by one.
    candidate_params = ("search_text", "search", "q", "query")

    for param_name in candidate_params:
        status, payload = fetch_page(page, per_page, param_name, query)
        if status != 200:
            continue

        items = extract_items(payload)
        matching = [item for item in items if item_matches(item, query)]

        # If upstream actually filtered, at least one returned row should match.
        # We return only matching rows, never unrelated inventory.
        if matching:
            pagination = extract_pagination(payload, page, per_page, len(matching))
            pagination["count"] = len(matching)
            return 200, {
                "success": True,
                "mode": "search",
                "query": query,
                "search_parameter_used": param_name,
                "items": matching,
                "pagination": pagination,
            }

    # Fallback: inspect the first normal page, but do not pretend this is global search.
    status, payload = fetch_page(1, min(per_page, 200))
    if status == 200:
        first_page_items = extract_items(payload)
        matching = [item for item in first_page_items if item_matches(item, query)]
        if matching:
            return 200, {
                "success": True,
                "mode": "local_page_fallback",
                "query": query,
                "items": matching,
                "pagination": {
                    "page": 1,
                    "per_page": len(first_page_items),
                    "count": len(matching),
                    "total": len(matching),
                    "total_pages": 1,
                    "has_more": False,
                },
                "warning": (
                    "The Apex /api/zoho/items endpoint appears to ignore search parameters. "
                    "These matches are only from the first fetched page, not the full inventory."
                ),
            }

    return 200, {
        "success": True,
        "mode": "unsupported_global_search",
        "query": query,
        "items": [],
        "pagination": {
            "page": 1,
            "per_page": per_page,
            "count": 0,
            "total": 0,
            "total_pages": 1,
            "has_more": False,
        },
        "warning": (
            "The Apex /api/zoho/items endpoint is returning unfiltered inventory and appears "
            "not to support server-side text search with search_text, search, q, or query. "
            "Use Exact SKU for a guaranteed lookup, or ask the API owner which search parameter "
            "the list endpoint supports."
        ),
    }


def lookup_item(sku: str) -> tuple[int, dict[str, Any]]:
    sku = sku.strip()
    if not sku:
        return 400, {"success": False, "error": "SKU is required."}

    status, payload = upstream_get(f"/api/zoho/items/{quote(sku, safe='')}")

    if status != 200:
        return status, {
            "success": False,
            **(payload if isinstance(payload, dict) else {"error": str(payload)}),
        }

    if isinstance(payload, dict) and payload.get("found") is False:
        return 404, {"success": False, "error": f"No item found for SKU {sku}."}

    item = payload.get("item") if isinstance(payload, dict) else payload
    return 200, {"success": True, "sku": sku, "item": item}


class Handler(BaseHTTPRequestHandler):
    def send_json(self, status: int, payload: dict[str, Any]) -> None:
        body = json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def send_html(self) -> None:
        if not HTML_PATH.exists():
            self.send_error(500, f"Missing HTML file: {HTML_PATH}")
            return

        body = HTML_PATH.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        qs = parse_qs(parsed.query)

        if parsed.path == "/":
            self.send_html()
            return

        if parsed.path == "/api/items":
            try:
                page = int(qs.get("page", ["1"])[0])
                per_page = int(qs.get("per_page", ["50"])[0])
            except ValueError:
                self.send_json(400, {"success": False, "error": "Invalid pagination."})
                return

            query = (qs.get("q", [""])[0] or "").strip()
            status, payload = search_items(query, page, per_page)
            self.send_json(status, payload)
            return

        if parsed.path == "/api/item":
            sku = (qs.get("sku", [""])[0] or "").strip()
            status, payload = lookup_item(sku)
            self.send_json(status, payload)
            return

        self.send_error(404, "Not found")

    def log_message(self, fmt: str, *args: Any) -> None:
        print(f"[{self.log_date_time_string()}] {fmt % args}")


def main() -> None:
    load_local_env()

    print("=" * 66)
    print(APP_VERSION)
    print(f"API KEY FOUND : {bool(get_api_key())}")
    print(f"HTML FOUND    : {HTML_PATH.exists()}")
    print("=" * 66)

    server = ThreadingHTTPServer((HOST, PORT), Handler)
    print(f"Open http://{HOST}:{PORT}")
    print("Press Ctrl+C to stop.")

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()