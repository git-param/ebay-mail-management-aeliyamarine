import json
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, quote, urlencode, urlparse

import requests

APP_VERSION = "ZOHO-INVENTORY-BROWSER-v1"
BASE_URL = "https://apex.200.141.3.14.sslip.io"
REQUEST_TIMEOUT = 30
HOST = "127.0.0.1"
PORT = 5000

HERE = Path(__file__).resolve().parent
HTML_PATH = HERE / "zoho_inventory_browser.html"
ENV_PATH = HERE / ".env"


def load_local_env() -> None:
    if not ENV_PATH.exists():
        return

    for raw_line in ENV_PATH.read_text(encoding="utf-8-sig").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue

        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key:
            os.environ[key] = value


def get_api_key() -> str:
    load_local_env()
    return (os.getenv("ZOHO_LOOKUP_API_KEY") or "").strip()


def api_headers() -> dict[str, str]:
    api_key = get_api_key()
    if not api_key:
        raise RuntimeError(
            f"API key not found. Put ZOHO_LOOKUP_API_KEY=... in {ENV_PATH}"
        )

    return {
        "X-API-Key": api_key,
        "Accept": "application/json",
    }


def request_json(url: str, params: dict[str, Any] | None = None) -> tuple[int, Any]:
    try:
        response = requests.get(
            url,
            headers=api_headers(),
            params=params,
            timeout=REQUEST_TIMEOUT,
        )
    except RuntimeError as exc:
        return 500, {"error": str(exc)}
    except requests.Timeout:
        return 504, {"error": "Apex API request timed out."}
    except requests.RequestException as exc:
        return 502, {
            "error": "Could not reach the Apex API.",
            "details": str(exc),
        }

    try:
        payload = response.json()
    except ValueError:
        return 502, {
            "error": "Apex API returned non-JSON.",
            "upstream_status": response.status_code,
            "details": response.text[:2000],
        }

    if not response.ok:
        message = "Apex API returned an error."
        if isinstance(payload, dict):
            message = (
                payload.get("message")
                or payload.get("error")
                or payload.get("detail")
                or message
            )

        return response.status_code, {
            "error": message,
            "upstream_status": response.status_code,
            "details": payload,
        }

    return 200, payload


def extract_single_item(payload: Any) -> Any:
    if not isinstance(payload, dict):
        return payload

    for key in ("item", "data", "result"):
        value = payload.get(key)
        if isinstance(value, dict):
            return value

    return payload


def extract_items(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]

    if not isinstance(payload, dict):
        return []

    for key in ("items", "data", "results", "records"):
        value = payload.get(key)

        if isinstance(value, list):
            return [item for item in value if isinstance(item, dict)]

        # Some APIs wrap records again inside data.
        if isinstance(value, dict):
            for nested_key in ("items", "results", "records", "data"):
                nested = value.get(nested_key)
                if isinstance(nested, list):
                    return [item for item in nested if isinstance(item, dict)]

    return []


def get_pagination(payload: Any, page: int, per_page: int, item_count: int) -> dict[str, Any]:
    pagination: dict[str, Any] = {
        "page": page,
        "per_page": per_page,
        "count": item_count,
    }

    if not isinstance(payload, dict):
        pagination["has_more"] = item_count >= per_page
        return pagination

    candidates = [payload]
    for key in ("pagination", "page_context", "meta"):
        value = payload.get(key)
        if isinstance(value, dict):
            candidates.append(value)

    aliases = {
        "page": ("page", "current_page", "page_number"),
        "per_page": ("per_page", "page_size", "limit"),
        "total": ("total", "total_count", "total_items", "records_total"),
        "total_pages": ("total_pages", "pages", "page_count", "last_page"),
        "has_more": ("has_more", "has_more_page", "more_records"),
    }

    for output_key, names in aliases.items():
        for source in candidates:
            found = False
            for name in names:
                if name in source and source[name] is not None:
                    pagination[output_key] = source[name]
                    found = True
                    break
            if found:
                break

    if "has_more" not in pagination:
        if "total_pages" in pagination:
            try:
                pagination["has_more"] = int(pagination["page"]) < int(pagination["total_pages"])
            except (TypeError, ValueError):
                pagination["has_more"] = item_count >= per_page
        elif "total" in pagination:
            try:
                pagination["has_more"] = int(pagination["page"]) * int(pagination["per_page"]) < int(pagination["total"])
            except (TypeError, ValueError):
                pagination["has_more"] = item_count >= per_page
        else:
            pagination["has_more"] = item_count >= per_page

    return pagination


def list_items(page: int, per_page: int) -> tuple[int, dict[str, Any]]:
    page = max(1, page)
    per_page = min(max(1, per_page), 100)

    # The endpoint was provided as paginated. page/per_page are forwarded directly.
    status, payload = request_json(
        f"{BASE_URL}/api/zoho/items",
        params={"page": page, "per_page": per_page},
    )

    if status != 200:
        return status, {
            "success": False,
            **(payload if isinstance(payload, dict) else {"error": str(payload)}),
        }

    items = extract_items(payload)
    return 200, {
        "success": True,
        "items": items,
        "pagination": get_pagination(payload, page, per_page, len(items)),
    }


def lookup_sku(sku: str) -> tuple[int, dict[str, Any]]:
    sku = sku.strip()
    if not sku:
        return 400, {"success": False, "error": "Please provide a SKU."}

    status, payload = request_json(
        f"{BASE_URL}/api/zoho/items/{quote(sku, safe='')}"
    )

    if status != 200:
        return status, {
            "success": False,
            **(payload if isinstance(payload, dict) else {"error": str(payload)}),
        }

    if isinstance(payload, dict) and payload.get("found") is False:
        return 404, {
            "success": False,
            "error": f"No item found for SKU {sku}.",
        }

    return 200, {
        "success": True,
        "sku": sku,
        "item": extract_single_item(payload),
    }


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
            self.send_error(500, f"HTML file not found: {HTML_PATH}")
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
        params = parse_qs(parsed.query)

        if parsed.path == "/":
            self.send_html()
            return

        if parsed.path == "/api/items":
            try:
                page = int((params.get("page", ["1"])[0] or "1"))
                per_page = int((params.get("per_page", ["25"])[0] or "25"))
            except ValueError:
                self.send_json(400, {
                    "success": False,
                    "error": "page and per_page must be numbers.",
                })
                return

            status, payload = list_items(page, per_page)
            self.send_json(status, payload)
            return

        if parsed.path == "/api/item":
            sku = (params.get("sku", [""])[0] or "").strip()
            status, payload = lookup_sku(sku)
            self.send_json(status, payload)
            return

        if parsed.path == "/api/debug":
            key = get_api_key()
            self.send_json(200, {
                "version": APP_VERSION,
                "running_file": str(Path(__file__).resolve()),
                "env_path": str(ENV_PATH),
                "env_exists": ENV_PATH.exists(),
                "api_key_detected": bool(key),
                "html_path": str(HTML_PATH),
                "html_exists": HTML_PATH.exists(),
            })
            return

        self.send_error(404, "Not found")

    def log_message(self, fmt: str, *args: Any) -> None:
        print(f"[{self.log_date_time_string()}] {fmt % args}")


def main() -> None:
    load_local_env()

    print("=" * 68)
    print(APP_VERSION)
    print(f"RUNNING FILE : {Path(__file__).resolve()}")
    print(f".ENV EXISTS  : {ENV_PATH.exists()}")
    print(f"API KEY FOUND: {bool(get_api_key())}")
    print(f"HTML EXISTS  : {HTML_PATH.exists()}")
    print("=" * 68)

    server = ThreadingHTTPServer((HOST, PORT), Handler)
    print(f"Open http://{HOST}:{PORT}")
    print("Press Ctrl+C to stop.")

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopping server...")
    finally:
        server.server_close()


if __name__ == "__main__":
    main()