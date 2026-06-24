# eBay Conversation Product Context

This feature enriches eBay conversations with the product/listing information needed to show a compact product banner above the message thread.

It replaces the old conversation "Order Context" UI. Order ID and SKU are now optional enrichments, while product title, image, seller, and item link come from the conversation's listing reference.

## Data Flow

### 1. Commerce Message API

During eBay message sync, the app calls:

```text
GET /commerce/message/v1/conversation
GET /commerce/message/v1/conversation/{conversationId}
```

The list response provides the important listing reference fields:

```json
{
  "conversationId": "126074245304",
  "referenceType": "LISTING",
  "referenceId": "406782846451"
}
```

Stored on `conversations`:

```text
provider_conversation_id = conversationId
reference_type = referenceType
reference_id = referenceId
raw_payload.summary = getConversations item
raw_payload.detail = getConversation response
```

The Commerce Message API does not provide `orderId`.

### 2. Browse API

If:

```text
reference_type == LISTING
reference_id exists
```

the sync calls:

```text
GET /buy/browse/v1/item/get_item_by_legacy_id?legacy_item_id={referenceId}
```

The Browse API returns product data such as:

```json
{
  "legacyItemId": "406782846451",
  "title": "VOLCANO R4440V200-A Frame Detector Relay/Flame Monitor",
  "image": {
    "imageUrl": "https://i.ebayimg.com/images/g/z5MAAOSwoYFlsh-4/s-l1600.jpg"
  },
  "seller": {
    "username": "aeliya-trade110"
  }
}
```

Stored on `conversation_product_contexts`:

```text
reference_id      = conversation.reference_id
reference_type    = conversation.reference_type
item_title        = Browse API title
image_url         = Browse API image.imageUrl
seller_username   = Browse API seller.username
item_url          = https://www.ebay.com/itm/{referenceId}
raw_payload       = full Browse API response
enrichment_status = ENRICHED or FAILED
last_enriched_at  = current timestamp
```

### 3. Optional SKU and Order Matching

After Browse enrichment, the app tries to fill optional fields from local data:

```text
sku
order_id
```

It searches existing locally synced `order_line_items` where:

```text
order_line_items.item_id = referenceId
OR
order_line_items.listing_id = referenceId
```

If found:

```text
conversation_product_contexts.sku = order_line_items.sku
conversation_product_contexts.order_id = order_line_items.order_id
```

If not found, enrichment still succeeds with product title/image/seller. SKU and order are stored as `NULL`.

## Database Table

Table:

```text
conversation_product_contexts
```

Columns:

```text
id
conversation_id
reference_id
reference_type
item_title
image_url
seller_username
item_url
sku
order_id
enrichment_status
raw_payload
last_enriched_at
created_at
updated_at
```

Statuses:

```text
PENDING  - context row exists but enrichment has not completed
ENRICHED - Browse API succeeded; SKU/order may still be null
FAILED   - Browse API failed; retry later/backfill can try again
```

## Backend Code

Main service:

```text
backend/app/services/conversation_product_context_service.py
```

Responsibilities:

```text
context_for_conversation()
  Returns existing product context or enriches it if missing.

enrich_conversation()
  Extracts reference fields, calls Browse API, stores product context, and tries local SKU/order matching.

serialize()
  Converts the model into the API response shape.
```

Sync integration:

```text
backend/app/modules/integrations/ebay/services/ebay_sync_service.py
```

During every conversation sync:

```text
1. Upsert conversation from Commerce Message data.
2. Flush conversation so it has a database ID.
3. Enrich product context using referenceId/referenceType.
4. Upsert messages and attachments.
```

Backfill job:

```text
backend/scripts/backfill_conversation_product_context.py
```

Run after migrations to enrich existing conversations:

```bash
python backend/scripts/backfill_conversation_product_context.py
```

## API Endpoint

Endpoint:

```text
GET /conversations/{conversation_id}/context
```

Response:

```json
{
  "reference_id": "406782846451",
  "title": "VOLCANO R4440V200-A Frame Detector Relay/Flame Monitor",
  "image_url": "https://i.ebayimg.com/images/g/z5MAAOSwoYFlsh-4/s-l1600.jpg",
  "seller_username": "aeliya-trade110",
  "item_url": "https://www.ebay.com/itm/406782846451",
  "sku": null,
  "order_id": null,
  "enrichment_status": "ENRICHED"
}
```

The main conversation detail endpoint also includes the same object:

```text
GET /conversations/{conversation_id}
```

Response field:

```json
{
  "product_context": {
    "reference_id": "406782846451",
    "title": "...",
    "image_url": "...",
    "seller_username": "aeliya-trade110",
    "item_url": "https://www.ebay.com/itm/406782846451",
    "sku": null,
    "order_id": null,
    "enrichment_status": "ENRICHED"
  }
}
```

## Frontend Handling

File:

```text
frontend/src/pages/dashboard.jsx
```

Component:

```text
ProductContextBanner
```

Displayed above the message thread.

Shows:

```text
Product image
Product title
Item ID
Seller username
SKU or "--"
Order or "--"
```

Actions:

```text
Open Listing - opens item_url in a new tab
Copy Item ID - copies reference_id
Copy SKU     - shown only when SKU exists
```

Fallback behavior:

```text
No image       - shows package placeholder
No product yet - shows "Product information is still being enriched."
No SKU/order   - shows "--"
```

## Error Handling

Conversation loading must not fail because product enrichment fails.

If Browse API fails:

```text
enrichment_status = FAILED
raw_payload = error details
```

The conversation still loads normally.

If SKU/order matching fails:

```text
sku = NULL
order_id = NULL
```

The product card still displays title/image/seller from Browse API.

## Logging

The enrichment service logs:

```text
Conversation ID
Reference ID
Reference Type
Browse API success/failure
Title fetched true/false
Image fetched true/false
Seller fetched true/false
SKU matched true/false
Order matched true/false
```

## Migration

Migration file:

```text
backend/alembic/versions/20260624_0018_conversation_product_contexts.py
```

Run:

```bash
alembic upgrade head
```
