# API endpoint catalog

Start with these files when locating an API call:

- `frontend/src/constants/api.js`: the frontend's backend endpoint strings, grouped in `API`, plus the default API prefix and Vite proxy address.
- `backend/app/constants/api.py`: backend router prefixes (`ApiPrefixes`), route paths grouped by module, outbound provider URLs (`ExternalApi`), and eBay XML operation names (`EbayTradingCalls`). This includes eBay production/sandbox URLs, OAuth scopes, notification paths, Zoho, Blogger, Alreza, and translation.

Each runtime imports its own catalog. Business logic and HTTP methods stay in the service/router that uses the endpoint. Queries, identifiers, credentials, and payloads are supplied at runtime. Provider-returned URLs, such as image resource locations, remain runtime data.

## Trace an existing call

For a conversation detail request:

1. Find `API.CONVERSATIONS.BY_CONVERSATION_ID` in `api.js`.
2. Find its reference in `frontend/src/services/conversationApi.js`.
3. `apiRequest` in `frontend/src/services/http.js` sends the request with the API base URL.
4. `backend/app/main.py` mounts `ApiPrefixes.API_V1`; `backend/app/api/v1/router.py` mounts `ApiPrefixes.CONVERSATIONS`.
5. `backend/app/api/v1/routes/conversations.py` handles `ConversationsRoutes.BY_CONVERSATION_ID`.

For an eBay request, search an `ExternalApi` symbol such as `EBAY_PRODUCTION_CONVERSATIONS`. Its references lead to the client property and HTTP call in `ebay_auth_client.py`.

## Add or change an endpoint

Define a named string in the appropriate catalog and import it at the caller:

```js
import { API, apiPath } from '../constants/api'

return apiRequest(apiPath(API.CONVERSATIONS.BY_CONVERSATION_ID, { conversationId }))
```

`apiPath` substitutes named placeholders and throws when a required value is absent. It does not encode values automatically; preserve the caller's encoding requirements, using `encodeURIComponent` when needed. Query builders remain in the service files.

```python
from app.constants.api import ConversationsRoutes, ExternalApi

@router.get(ConversationsRoutes.BY_CONVERSATION_ID)
def get_conversation(...):
    ...

request_url = ExternalApi.EBAY_CONVERSATION_DETAIL.format(
    conversations_url=client.conversations_url,
    conversation_id=conversation_id,
    query=query,
)
```

Keep corresponding frontend/backend paths aligned when changing an endpoint. Environment-specific overrides such as `VITE_API_BASE_URL`, `TRANSLATION_API_URL`, `EBAY_MEDIA_BASE_URL`, and `PUBLIC_BACKEND_URL` continue to work. Do not place secrets in the catalogs. Regular browser navigation and external website links are separate from API endpoint definitions.

## Checks

From `backend`, run:

```text
.venv/Scripts/python.exe -m pytest tests/test_api_catalog.py -q
```

From `frontend`, run:

```text
npm run test:api
npm run build
```

The catalog checks reject inline backend route definitions, provider URL literals, and frontend service endpoint literals. Test fixtures and documentation can include example URLs.
