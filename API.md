# ACES API Documentation

This index separates APIs exposed by ACES from APIs that ACES calls on eBay.

## API References

1. [System API](docs/api/system-api.md) documents the FastAPI endpoints consumed by the React frontend and internal operators.
2. [eBay API](docs/api/ebay-api.md) documents outbound OAuth, REST, and Trading API calls made by the backend.

Every endpoint entry records:

1. **API endpoint**: HTTP method and path.
2. **Response structure**: the Pydantic/OpenAPI model or the important returned fields.
3. **What it does**: the endpoint's responsibility in the system.

## Base URLs

| Service | Local base URL |
|---|---|
| ACES API | `http://127.0.0.1:8000/api/v1` |
| Health endpoint | `http://127.0.0.1:8000/health` |
| Swagger UI | `http://127.0.0.1:8000/docs` |
| OpenAPI JSON | `http://127.0.0.1:8000/openapi.json` |
| LibreTranslate | `http://127.0.0.1:5001` |

## Conventions

- Paths in the system reference are relative to the backend host.
- JSON is used unless an endpoint explicitly returns a redirect, file, spreadsheet, or empty `204` response.
- UUID fields are serialized as strings; date/time fields use ISO 8601.
- List endpoints may use `limit`/`offset` pagination or module-specific filters.
- Protected endpoints accept the access token from the configured HTTP-only cookie or authorization flow.
- `401` means authentication is missing/expired, `403` means the user lacks permission, `404` means the resource was not found, and `422` means request validation failed.
- FastAPI's live `/docs` and `/openapi.json` remain the exact machine-readable contract for the running revision.

## Related Documentation

- [Architecture](ARCHITECTURE.md)
- [Project setup and startup](README.md)
