# Message Type / Messaging Analytics API

All routes use the existing access-token authentication. Message types are internal metadata and are never included in marketplace requests.

## Reply integration

`POST /api/v1/conversations/{conversation_id}/reply` requires `message_type_id` in either JSON or multipart form data. The ID must identify an active, non-deleted leaf type. Classification is inserted only after the marketplace send succeeds and is committed in the same transaction as the outbound `messages` row. Provider failure rolls both rows back.

## Message types

- `GET /api/v1/message-types` — hierarchy; `include_deleted=true` includes the recycle bin.
- `GET /api/v1/message-types/tree` — active dropdown hierarchy.
- `POST /api/v1/message-types` — admin create.
- `PUT /api/v1/message-types/{id}` — admin edit/reorder/reparent; cycles are rejected.
- `DELETE /api/v1/message-types/{id}` — admin soft delete. Used types are disabled to preserve history.
- `PATCH /api/v1/message-types/{id}/status` — admin enable, disable, or restore.

## Reports

`GET /api/v1/reports/message-types` is available to admins and operations managers. Filters: `date_from`, `date_to`, `seller_account_id`, `user_id`, `category_id`, `subcategory_id`, `conversation_id`, `search`, `limit`, `offset`, `sort_by`, and `sort_dir`. It returns detail rows plus API-ready aggregates by date, employee, category, and seller account.

`GET /api/v1/reports/message-types/export` accepts the same data filters, ignores pagination, and returns `message_report_YYYY_MM_DD.xlsx`.

Run `alembic upgrade head` to create and seed the tables. Existing replies remain valid and are absent from classification reports.
