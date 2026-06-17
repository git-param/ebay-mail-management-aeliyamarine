# Inbox API

## List conversations

`GET /api/v1/conversations`

Query parameters:

- `limit` default `25`, max `100`
- `offset` default `0`
- `search` searches subject, buyer, provider conversation ID, reference ID, and message body
- `status` one of `OPEN`, `PENDING`, `RESOLVED`, `CLOSED`
- `provider` for example `ebay`
- `ebay_account_id`
- `assigned_user_id` filters by current assignee
- `category_id`

Example response:

```json
{
  "items": [
    {
      "id": "ff6980c4-edc5-4497-ac72-d0db366d3fbb",
      "provider": "ebay",
      "provider_conversation_id": "125432475305",
      "provider_account_id": "c9add41a-368d-4a0d-ad3e-ad97fb83f2a0",
      "subject": null,
      "buyer_identifier": "ibrkha-3737",
      "provider_conversation_status": "ACTIVE",
      "provider_conversation_type": "FROM_MEMBERS",
      "reference_id": "405955463523",
      "reference_type": "LISTING",
      "unread_count": 0,
      "status": "OPEN",
      "category_id": null,
      "category": null,
      "last_message_at": "2026-06-17T12:19:32+05:30",
      "external_created_at": null,
      "created_at": "2026-06-17T12:45:00+05:30",
      "updated_at": "2026-06-17T12:45:00+05:30",
      "current_assignment": null
    }
  ],
  "total": 1,
  "limit": 25,
  "offset": 0
}
```

## Get conversation detail

`GET /api/v1/conversations/{id}`

Returns metadata, messages, category, current assignment, assignment history, and internal notes.

## Assign conversation

`POST /api/v1/conversations/{id}/assign`

```json
{
  "assigned_to": "11111111-1111-1111-1111-111111111111"
}
```

Any authenticated user may assign to any active user. Previous current assignments are closed by setting `unassigned_at`, preserving assignment history.

## Internal notes

`POST /api/v1/conversations/{id}/notes`

```json
{
  "body": "Called customer, waiting for part confirmation."
}
```

`GET /api/v1/conversations/{id}/notes`

Notes are internal application records only. They are never synced back to eBay.

## Category management

Categories are managed via existing endpoints:

- `GET /api/v1/categories`
- `POST /api/v1/categories`
- `GET /api/v1/categories/{category_id}`
- `PUT /api/v1/categories/{category_id}`
- `PATCH /api/v1/categories/{category_id}/activate`
- `PATCH /api/v1/categories/{category_id}/deactivate`
- `DELETE /api/v1/categories/{category_id}`
- `POST /api/v1/categories/{category_id}/keywords`
- `DELETE /api/v1/categories/{category_id}/keywords/{keyword_id}`
