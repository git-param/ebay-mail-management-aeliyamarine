import json
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, quote, urlparse

import requests


BASE_URL = os.getenv("ZOHO_LOOKUP_BASE_URL", "https://apex.200.141.3.14.sslip.io").rstrip("/")
API_KEY = os.getenv("ZOHO_LOOKUP_API_KEY", "e0db6c9db43132cedd6013c375f3a0b89f8146f4bb6a6e16")
REQUEST_TIMEOUT = 20
HOST = "127.0.0.1"
PORT = int(os.getenv("ZOHO_SEARCH_PORT", "5000"))

HERE = Path(__file__).resolve().parent
HTML_PATH = HERE / "zoho_search.html"


def extract_item(payload: Any) -> Any:
    """Try common API wrappers without assuming one exact response schema."""
    if not isinstance(payload, dict):
        return payload

    for key in ("item", "data", "result"):
        value = payload.get(key)
        if isinstance(value, dict):
            return value

    return payload


def lookup_sku(sku: str) -> tuple[int, dict[str, Any]]:
    if not sku:
        return 400, {"success": False, "error": "Please enter a SKU."}

    if not API_KEY or API_KEY == "e0db6c9db43132cedd6013c375f3a0b89f8146f4bb6a6e16":
        return 500, {
            "success": False,
            "error": (
                "API key is not configured. Set the ZOHO_LOOKUP_API_KEY "
                "environment variable before starting the app."
            ),
        }

    # Uses the endpoint supplied to you:
    # GET /api/zoho/items/<SKU> with X-API-Key.
    upstream_url = f"{BASE_URL}/api/zoho/items/{quote(sku, safe='')}"

    try:
        response = requests.get(
            upstream_url,
            headers={"X-API-Key": API_KEY, "Accept": "application/json"},
            timeout=REQUEST_TIMEOUT,
        )
    except requests.Timeout:
        return 504, {"success": False, "error": "Zoho lookup API timed out."}
    except requests.RequestException as exc:
        return 502, {
            "success": False,
            "error": "Could not reach the Zoho lookup API.",
            "details": str(exc),
        }

    try:
        payload = response.json()
    except ValueError:
        return 502, {
            "success": False,
            "error": "Zoho lookup API returned a non-JSON response.",
            "status_code": response.status_code,
        }

    if response.status_code == 404:
        return 404, {"success": False, "error": f"No item found for SKU {sku}."}

    if not response.ok:
        upstream_message = None
        if isinstance(payload, dict):
            upstream_message = (
                payload.get("message")
                or payload.get("error")
                or payload.get("detail")
            )

        status = response.status_code if 400 <= response.status_code < 600 else 502
        return status, {
            "success": False,
            "error": upstream_message or "Zoho lookup API returned an error.",
            "status_code": response.status_code,
        }

    return 200, {
        "success": True,
        "sku": sku,
        "item": extract_item(payload),
        "raw": payload,
    }


class SearchHandler(BaseHTTPRequestHandler):
    def send_json(self, status: int, payload: dict[str, Any]) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def send_html(self) -> None:
        if not HTML_PATH.exists():
            self.send_error(500, "zoho_search.html was not found next to the Python file.")
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

        if parsed.path == "/":
            self.send_html()
            return

        if parsed.path == "/api/search":
            params = parse_qs(parsed.query)
            sku = (params.get("sku", [""])[0] or "").strip()
            status, payload = lookup_sku(sku)
            self.send_json(status, payload)
            return

        self.send_error(404, "Not found")

    def log_message(self, format: str, *args: Any) -> None:
        print(f"[{self.log_date_time_string()}] {format % args}")


def main() -> None:
    server = ThreadingHTTPServer((HOST, PORT), SearchHandler)
    print(f"Zoho Inventory Search running at http://{HOST}:{PORT}")
    print("Press Ctrl+C to stop.")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopping server...")
    finally:
        server.server_close()


if __name__ == "__main__":
    main()