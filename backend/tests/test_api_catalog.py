"""Keep API addresses discoverable through the central catalog."""
import ast
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

import pytest

from app.modules.integrations.ebay.client.ebay_auth_client import EbayAuthClient


APP = Path(__file__).resolve().parents[1] / 'app'
HTTP_METHODS = {'get', 'post', 'put', 'patch', 'delete', 'head', 'options', 'websocket', 'api_route'}


def test_routes_and_router_prefixes_use_imported_constants():
    errors = []
    for file in APP.rglob('*.py'):
        tree = ast.parse(file.read_text(encoding='utf-8-sig'))
        catalog_names = {
            item.asname or item.name
            for node in tree.body
            if isinstance(node, ast.ImportFrom) and node.module == 'app.constants.api'
            for item in node.names
        }
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            fn = node.func
            values = []
            if (isinstance(fn, ast.Attribute) and fn.attr in HTTP_METHODS
                    and isinstance(fn.value, ast.Name) and fn.value.id in {'app', 'router', 'reports_router'}):
                values = node.args[:1]
            if (isinstance(fn, ast.Attribute) and fn.attr == 'include_router'
                    or isinstance(fn, ast.Name) and fn.id == 'APIRouter'):
                values += [kw.value for kw in node.keywords if kw.arg == 'prefix']
            for value in values:
                if not (isinstance(value, ast.Attribute) and isinstance(value.value, ast.Name)
                        and value.value.id in catalog_names):
                    errors.append(f'{file.relative_to(APP)}:{node.lineno}')
    assert not errors, f'API route paths must come from app.constants.api: {errors}'


def test_runtime_provider_urls_are_not_defined_outside_catalog():
    errors = []
    for file in APP.rglob('*.py'):
        if file == APP / 'constants/api.py':
            continue
        tree = ast.parse(file.read_text(encoding='utf-8-sig'))
        for node in ast.walk(tree):
            if (isinstance(node, ast.Constant) and isinstance(node.value, str)
                    and node.value.startswith(('https://', 'http://'))
                    and len(node.value) > 10 and '\n' not in node.value):
                errors.append(f'{file.relative_to(APP)}:{node.lineno}')
    assert not errors, f'Provider URLs must come from app.constants.api: {errors}'


@pytest.mark.parametrize('environment,host', [('PRODUCTION', 'api.ebay.com'), ('SANDBOX', 'api.sandbox.ebay.com')])
def test_ebay_detail_requests_preserve_environment_and_pagination(environment, host, monkeypatch):
    client = EbayAuthClient(client_id='test', client_secret='test', redirect_uri='test', runame='test', environment=environment)
    monkeypatch.setattr(client, '_request_message_api_raw', lambda token, **values: values['request_url'])
    url = client.get_conversation_raw('test-token', conversation_id='thread-123', conversation_type='FROM_MEMBERS', limit=50, offset=100)
    parsed = urlsplit(url)
    assert parsed.scheme == 'https'
    assert parsed.netloc == host
    assert parsed.path == '/commerce/message/v1/conversation/thread-123'
    assert parse_qs(parsed.query) == {'conversation_type': ['FROM_MEMBERS'], 'limit': ['50'], 'offset': ['100']}
