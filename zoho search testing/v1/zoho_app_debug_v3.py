import json
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, quote, urlparse

import requests

APP_VERSION = "ZOHO-SEARCH-DEBUG-v3"
BASE_URL = "https://apex.200.141.3.14.sslip.io"
REQUEST_TIMEOUT = 20
HOST = "127.0.0.1"
PORT = 5000

HERE = Path(__file__).resolve().parent
HTML_PATH = HERE / "zoho_search.html"
ENV_PATH = HERE / ".env"


def load_local_env() -> None:
    """Load KEY=VALUE entries from .env next to this script."""
    if not ENV_PATH.exists():
        return

    for raw_line in ENV_PATH.read_text(encoding="utf-8-sig").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue

        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")

        # For this test app, .env should override any stale shell value.
        if key:
            os.environ[key] = value


def get_api_key() -> str:
    load_local_env()
    return (os.getenv("ZOHO_LOOKUP_API_KEY") or "").strip()


def extract_item(payload: Any) -> Any:
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

    api_key = get_api_key()

    print(f"[DEBUG] .env path: {ENV_PATH}")
    print(f"[DEBUG] .env exists: {ENV_PATH.exists()}")
    print(f"[DEBUG] API key detected: {bool(api_key)}")
    if api_key:
        print(f"[DEBUG] API key length: {len(api_key)}")

    if not api_key:
        return 500, {
            "success": False,
            "error": "API key not found.",
            "debug": {
                "running_file": str(Path(__file__).resolve()),
                "env_path": str(ENV_PATH),
                "env_exists": ENV_PATH.exists(),
            },
        }

    upstream_url = f"{BASE_URL}/api/zoho/items/{quote(sku, safe='')}"

    print(f"[Zoho API] GET {upstream_url}")
    print("[Zoho API] Sending X-API-Key header")

    try:
        response = requests.get(
            upstream_url,
            headers={
                "X-API-Key": api_key,
                "Accept": "application/json",
            },
            timeout=REQUEST_TIMEOUT,
        )
    except requests.Timeout:
        print("[Zoho API] Request timed out")
        return 504, {"success": False, "error": "Apex API request timed out."}
    except requests.RequestException as exc:
        print(f"[Zoho API] Request error: {exc}")
        return 502, {
            "success": False,
            "error": "Could not reach the Apex API.",
            "details": str(exc),
        }

    print(f"[Zoho API] HTTP {response.status_code}")
    print(f"[Zoho API] Response: {response.text[:4000]}")

    try:
        payload = response.json()
    except ValueError:
        return 502, {
            "success": False,
            "error": "Apex API returned non-JSON.",
            "status_code": response.status_code,
            "details": response.text[:2000],
        }

    if response.status_code == 404:
        return 404, {
            "success": False,
            "error": f"No item found for SKU {sku}.",
            "details": payload,
        }

    if not response.ok:
        return response.status_code, {
            "success": False,
            "error": (
                payload.get("message")
                or payload.get("error")
                or payload.get("detail")
                or "Apex API returned an error."
                if isinstance(payload, dict)
                else "Apex API returned an error."
            ),
            "status_code": response.status_code,
            "details": payload,
        }

    return 200, {
        "success": True,
        "sku": sku,
        "item": extract_item(payload),
        "raw": payload,
    }


class SearchHandler(BaseHTTPRequestHandler):
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
            self.send_error(
                500,
                f"zoho_search.html not found. Expected: {HTML_PATH}"
            )
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

        if parsed.path == "/api/debug":
            key = get_api_key()
            self.send_json(200, {
                "version": APP_VERSION,
                "running_file": str(Path(__file__).resolve()),
                "working_directory": str(Path.cwd()),
                "env_path": str(ENV_PATH),
                "env_exists": ENV_PATH.exists(),
                "api_key_detected": bool(key),
                "api_key_length": len(key) if key else 0,
                "html_path": str(HTML_PATH),
                "html_exists": HTML_PATH.exists(),
            })
            return

        self.send_error(404, "Not found")

    def log_message(self, format: str, *args: Any) -> None:
        print(f"[{self.log_date_time_string()}] {format % args}")


def main() -> None:
    load_local_env()
    api_key = get_api_key()

    print("=" * 65)
    print(APP_VERSION)
    print(f"RUNNING FILE : {Path(__file__).resolve()}")
    print(f"WORKING DIR  : {Path.cwd()}")
    print(f".ENV PATH    : {ENV_PATH}")
    print(f".ENV EXISTS  : {ENV_PATH.exists()}")
    print(f"API KEY FOUND: {bool(api_key)}")
    print(f"API KEY LEN  : {len(api_key) if api_key else 0}")
    print(f"HTML EXISTS  : {HTML_PATH.exists()}")
    print("=" * 65)

    server = ThreadingHTTPServer((HOST, PORT), SearchHandler)
    print(f"Zoho Inventory Search running at http://{HOST}:{PORT}")
    print(f"Debug info: http://{HOST}:{PORT}/api/debug")
    print("Press Ctrl+C to stop.")

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopping server...")
    finally:
        server.server_close()


if __name__ == "__main__":
    main()