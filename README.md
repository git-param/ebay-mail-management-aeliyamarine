# ACES eBay Mail Management

ACES is an internal eBay helpdesk platform. It connects one or more eBay seller accounts, syncs eBay member/system conversations, stores every message locally, enriches threads with product and order context, detects offer events, and lets support users manage, assign, categorize, reply to, and report on conversations from a React inbox.

This README explains where each feature starts, which backend module handles it, which eBay APIs are called, what the responses look like, how many calls a sync makes, and how the data is stored.

---

## 1. Application Map

### Runtime Stack

| Layer | Technology | Entry Point |
|---|---|---|
| Frontend | React 19 + Vite | `frontend/src/App.jsx` |
| Backend | FastAPI + SQLAlchemy | `backend/app/main.py` |
| Database | PostgreSQL | `backend/app/db/session.py`, migrations in `backend/alembic/versions` |
| Auth | JWT access/refresh cookies | `backend/app/api/v1/routes/auth.py` |
| eBay integration | OAuth + Message + Fulfillment + Browse + Trading APIs | `backend/app/modules/integrations/ebay` |

### Main Frontend Routes

| UI Route | File | Purpose | Main Backend APIs |
|---|---|---|---|
| `/login` | `frontend/src/pages/login.jsx` | User login | `POST /api/v1/auth/login` |
| `/inbox`, `/dashboard` | `frontend/src/pages/dashboard.jsx` | Conversation inbox, thread view, reply composer, notes, assignment, category/status updates | `/api/v1/conversations/*` |
| `/ebay-accounts` | `frontend/src/pages/ebay_accounts.jsx` | Admin eBay account setup, OAuth, sync controls, API usage | `/api/v1/ebay-accounts/*`, `/api/v1/integrations/ebay/*` |
| `/categories` | `frontend/src/pages/categories.jsx` | Category and keyword management | `/api/v1/categories/*` |
| `/users` | `frontend/src/pages/users.jsx` | Admin user management | `/api/v1/users/*` |
| `/templates` | `frontend/src/pages/templates.jsx` | Reply templates and permissions | `/api/v1/templates/*` |
| `/analytics` | `frontend/src/pages/analytics.jsx` | Dashboard analytics/export | `/api/v1/analytics/*` |
| `/message-types` | `frontend/src/pages/message_types.jsx` | Message type taxonomy | `/api/v1/message-types/*` |
| `/message-reports` | `frontend/src/pages/message_reports.jsx` | Message type reports/export | `/api/v1/reports/message-types/*` |
| `/audit-logs` | `frontend/src/pages/audit_logs.jsx` | Admin audit log review/export | `/api/v1/audit-logs/*` |

### Backend Router Mounts

`backend/app/api/v1/router.py` mounts:

| Prefix | Route File |
|---|---|
| `/auth` | `backend/app/api/v1/routes/auth.py` |
| `/users` | `backend/app/api/v1/routes/users.py` |
| `/ebay-accounts` | `backend/app/api/v1/routes/ebay_accounts.py` |
| `/categories` | `backend/app/api/v1/routes/categories.py` |
| `/conversations` | `backend/app/api/v1/routes/conversations.py` |
| `/offers` | `backend/app/api/v1/routes/offers.py` |
| `/notifications` | `backend/app/api/v1/routes/notifications.py` |
| `/audit-logs` | `backend/app/api/v1/routes/audit_logs.py` |
| `/analytics` | `backend/app/api/v1/routes/analytics.py` |
| `/templates` | `backend/app/api/v1/routes/templates.py` |
| `/message-types` | `backend/app/api/v1/routes/message_types.py` |
| `/reports` | `backend/app/api/v1/routes/message_types.py` report router |
| `/integrations/ebay` | `backend/app/modules/integrations/ebay/routes/ebay_oauth_routes.py` |

---

## 2. Core Data Model

### eBay Account

Model: `backend/app/models/ebay_account.py`

`ebay_accounts` stores seller accounts and OAuth state:

```text
id
account_name
ebay_username
environment
connection_status
is_active
oauth_state
access_token
refresh_token
access_token_expires_at
refresh_token_expires_at
last_connected_at
ebay_user_id
store_name
last_sync_at
last_order_sync_at
sync_status
notes
created_by
created_at
updated_at
```

### Conversations and Messages

Model: `backend/app/models/conversation.py`

`conversations` stores one eBay thread:

```text
provider = EBAY
provider_conversation_id
provider_account_id
subject
buyer_identifier
provider_conversation_status
provider_conversation_type
reference_id
reference_type
linked_order_record_id
unread_count
status
category_id
category_manually_selected
last_message_at
external_created_at
raw_payload
```

`messages` stores each message inside a conversation:

```text
provider = EBAY
provider_message_id
conversation_id
sender_type = CUSTOMER | AGENT | SYSTEM | PROVIDER
sender_identifier
recipient_identifier
body
read_status
is_inbound
sent_at
raw_payload
offer_data
```

`message_attachments` stores inbound eBay media and locally saved outbound reply attachments:

```text
message_id
account_id
provider
provider_attachment_id
file_name
media_name
media_url
media_type
mime_type
file_size
storage_path
download_url
raw_payload
```

### Orders, Product Context, and Offers

Models: `backend/app/models/order_context.py`, `backend/app/models/offer.py`

Order sync stores:

```text
orders
order_line_items
conversation_order_contexts
returns
cancellations
```

Product enrichment stores:

```text
conversation_product_contexts
```

Offer sync/resolution stores:

```text
offers
```

Important offer fields:

```text
provider
account_id
conversation_id
message_id
provider_offer_id
listing_id
buyer_username
offer_amount
currency
status
direction
offer_type
quantity
raw_text
raw_payload
expires_at
created_at_provider
```

---

## 3. eBay Account Connection Flow

### Where It Starts

Frontend:

- `frontend/src/pages/ebay_accounts.jsx`
- `frontend/src/services/ebayAccountApi.js`

Backend:

- `POST /api/v1/ebay-accounts`
- `POST /api/v1/integrations/ebay/connect`
- `GET /api/v1/integrations/ebay/callback`
- `POST /api/v1/integrations/ebay/manual-callback`

Services:

- `EbayOAuthService`
- `EbayOAuthCallbackService`
- `EbayTokenService`
- `EbayAuthClient`

### Step-by-Step

1. Admin creates an account record in `/ebay-accounts`.
2. Backend stores it as `PENDING`, without tokens.
3. Admin clicks Connect.
4. `EbayOAuthService.create_authorization_url()` generates an eBay OAuth URL and stores a random `oauth_state`.
5. Seller authorizes the app at eBay.
6. eBay redirects to `/api/v1/integrations/ebay/callback?code=...&state=...`.
7. `EbayOAuthCallbackService.handle_callback()` validates the state, exchanges the code for tokens, calls eBay Identity API, verifies the connected username matches the account username, then stores tokens.
8. Account becomes `CONNECTED`.

### eBay OAuth Authorization URL

```http
GET https://auth.ebay.com/oauth2/authorize
  ?client_id=<EBAY_CLIENT_ID>
  &redirect_uri=<EBAY_RUNAME or EBAY_REDIRECT_URI>
  &response_type=code
  &state=<random_state>
  &scope=<space-separated scopes>
```

Configured scopes:

```text
https://api.ebay.com/oauth/api_scope/commerce.message
https://api.ebay.com/oauth/api_scope/commerce.identity.readonly
https://api.ebay.com/oauth/api_scope/sell.inventory
https://api.ebay.com/oauth/api_scope/sell.fulfillment
```

### eBay Token API

Used by:

- `exchange_code_for_tokens()`
- `refresh_access_token()`
- Browse app-token enrichment via client credentials

Request:

```http
POST https://api.ebay.com/identity/v1/oauth2/token
Authorization: Basic base64(client_id:client_secret)
Content-Type: application/x-www-form-urlencoded

grant_type=authorization_code&
code=<authorization_code>&
redirect_uri=<runame_or_redirect_uri>
```

Response example:

```json
{
  "access_token": "v^1.1#i^1#...",
  "refresh_token": "v^1.1#i^1#...",
  "expires_in": 7200,
  "refresh_token_expires_in": 47304000
}
```

Stored in:

```text
ebay_accounts.access_token
ebay_accounts.refresh_token
ebay_accounts.access_token_expires_at
ebay_accounts.refresh_token_expires_at
ebay_accounts.connection_status
ebay_accounts.last_connected_at
```

### eBay Identity API

Used to verify that the authenticated seller is the same eBay username entered by the admin.

Request:

```http
GET https://apiz.ebay.com/commerce/identity/v1/user/
Authorization: Bearer <access_token>
Accept: application/json
```

Response example:

```json
{
  "username": "aeliya-ship110",
  "userId": "123456789",
  "businessAccount": {
    "doingBusinessAs": "Aeliya Marine"
  }
}
```

Stored in:

```text
ebay_accounts.ebay_user_id
ebay_accounts.store_name
```

---

## 4. Full Account Sync Flow

### Where It Starts

Frontend:

- Single sync button: `syncEbayAccount(account.id)`
- Selected/all sync buttons: `syncAllEbayAccounts()`

Backend endpoints:

```http
POST /api/v1/integrations/ebay/sync/{account_id}
POST /api/v1/integrations/ebay/sync-all
```

Main orchestrator:

```text
backend/app/modules/integrations/ebay/services/ebay_sync_service.py
EbaySyncService.sync_account()
```

### High-Level Flow

```text
sync_account(account_id)
  -> load active CONNECTED eBay account
  -> refresh access token if missing/expired
  -> create sync_logs row
  -> fetch conversation pages for FROM_MEMBERS
  -> fetch conversation pages for FROM_EBAY
  -> for each conversation summary:
       -> fetch conversation detail
       -> upsert conversation
       -> enrich product/listing context
       -> upsert messages
       -> replace message attachments
       -> start SLA cycles and notifications for new inbound buyer messages
  -> sync order context
  -> sync buyer Best Offers
  -> sync seller offer notifications from My Messages
  -> update ebay_accounts.last_sync_at and sync_status
  -> complete sync_logs row
  -> return sync result to frontend
```

### Sync Result Response

Backend response shape:

```json
{
  "account_id": "uuid",
  "ebay_username": "aeliya-ship110",
  "sync_log_id": "uuid",
  "status": "SUCCESS",
  "conversations_processed": 50,
  "conversations_failed": 0,
  "failed_conversation_ids": [],
  "conversations_created": 10,
  "conversations_updated": 40,
  "messages_created": 75,
  "messages_updated": 200,
  "total_conversations_available": 918,
  "elapsed_seconds": 42.5,
  "average_detail_seconds": 0.38,
  "error_message": null,
  "api_usage": {
    "usage_date": "2026-07-09",
    "call_count": 14,
    "daily_limit": 100,
    "remaining": 86
  }
}
```

### How Many eBay API Calls Per Sync?

Let:

```text
FM = total FROM_MEMBERS conversations available
FE = total FROM_EBAY conversations available
N  = number of conversation summaries actually processed after max_conversations and incremental filtering
P  = number of conversations with LISTING reference_id needing Browse lookup and no reusable local/cache context
O  = total orders returned by Fulfillment API
B  = total GetBestOffers pages
```

Message sync calls:

```text
Conversation list calls = ceil(FM / 50) + ceil(FE / 50)
Conversation detail calls = N
```

Order sync calls:

```text
Fulfillment order calls = max(1, ceil(O / 200))
```

Product context calls:

```text
Browse app-token call = usually 0 or 1 per sync service instance/environment
Browse item calls = P
```

Offer sync calls:

```text
GetBestOffers calls = B
GetMyMessages calls = 1 currently, page 1 only, 200 headers
```

Token refresh calls:

```text
0 normally
1 if the token is expired before sync
up to 1 retry refresh per eBay API family when a 401 is returned
```

Total practical formula:

```text
Total eBay calls ~= conversation_list_pages
                 + N conversation_detail_calls
                 + order_pages
                 + browse_app_token_call
                 + P browse_item_calls
                 + B best_offer_pages
                 + 1 my_messages_call
                 + token_refresh_calls
```

Example:

```text
FM = 120, FE = 80, N = 200, P = 70, O = 240, B = 2

Conversation list = ceil(120/50) + ceil(80/50) = 3 + 2 = 5
Conversation detail = 200
Orders = ceil(240/200) = 2
Browse token = 1
Browse items = 70
Best offers = 2
My Messages = 1

Total before token retry = 281 eBay API calls
```

Important implementation note: `EbayApiUsageService` currently reserves quota in selected places (`sync_account` startup, order pages, BestOffer pages, MyMessages), but the actual external call count includes message list/detail and Browse calls too.

---

## 5. eBay Commerce Message API

Used by:

- `EbayAuthClient.get_conversations_raw()`
- `EbayAuthClient.get_conversation_raw()`
- `EbayAuthClient.send_conversation_message()`

### 5.1 Conversation List

Purpose:

- discover eBay conversation IDs
- fetch conversation title/status/type
- fetch `referenceId` and `referenceType`
- decide which detail calls to make

Request:

```http
GET https://api.ebay.com/commerce/message/v1/conversation?conversation_type=FROM_MEMBERS&limit=50&offset=0
Authorization: Bearer <access_token>
Accept: application/json
```

The sync runs this for both:

```text
FROM_MEMBERS
FROM_EBAY
```

Response example:

```json
{
  "limit": 50,
  "offset": 0,
  "total": 918,
  "href": "https://api.ebay.com/commerce/message/v1/conversation?conversation_type=FROM_EBAY&offset=0&limit=50",
  "next": "https://api.ebay.com/commerce/message/v1/conversation?conversation_type=FROM_EBAY&offset=50&limit=50",
  "conversations": [
    {
      "conversationId": "208491463945",
      "conversationStatus": "ACTIVE",
      "conversationTitle": "Question about item 405955487848",
      "conversationType": "FROM_MEMBERS",
      "createdDate": "2026-05-06T20:42:08.000Z",
      "referenceId": "405955487848",
      "referenceType": "LISTING",
      "unreadCount": 0,
      "latestMessage": {
        "messageId": "3497560590015",
        "senderUsername": "buyer123",
        "recipientUsername": "aeliya-ship110",
        "createdDate": "2026-05-06T20:42:08.000Z"
      }
    }
  ]
}
```

Processing:

- `EbaySyncService._iter_conversation_summaries()` reads `conversations[]`.
- It sets missing `conversationType` from the current loop.
- It filters old conversations when `account.last_sync_at` exists.
- It stops paginating a type if an incremental page is entirely older than the cursor.

Stored later in `conversations.raw_payload.summary`.

### 5.2 Conversation Detail

Purpose:

- fetch the actual messages
- fetch sender/recipient usernames
- fetch message bodies and timestamps
- fetch `messageMedia[]` attachments

Request:

```http
GET https://api.ebay.com/commerce/message/v1/conversation/208491463945?conversation_type=FROM_MEMBERS&limit=50&offset=0
Authorization: Bearer <access_token>
Accept: application/json
```

Response example:

```json
{
  "limit": 50,
  "offset": 0,
  "total": 2,
  "conversationTitle": "Question about item 405955487848",
  "conversationStatus": "ACTIVE",
  "conversationType": "FROM_MEMBERS",
  "referenceId": "405955487848",
  "referenceType": "LISTING",
  "messages": [
    {
      "messageId": "6275165199019",
      "messageBody": "Available?",
      "senderUsername": "buyer123",
      "recipientUsername": "aeliya-ship110",
      "readStatus": true,
      "createdDate": "2026-06-16T21:08:23.000Z"
    },
    {
      "messageId": "3497560590015",
      "messageBody": "Yes, it is available.",
      "senderUsername": "aeliya-ship110",
      "recipientUsername": "buyer123",
      "readStatus": true,
      "createdDate": "2026-06-17T06:49:32.000Z"
    }
  ]
}
```

`FROM_EBAY` system-message example:

```json
{
  "limit": 50,
  "offset": 0,
  "total": 1,
  "conversationTitle": "Your monthly statement is ready",
  "conversationStatus": "ACTIVE",
  "conversationType": "FROM_EBAY",
  "messages": [
    {
      "messageId": "208519361635",
      "messageBody": "<!DOCTYPE html><html>...eBay email body...</html>",
      "senderUsername": "eBay",
      "recipientUsername": "aeliya-ship110",
      "subject": "Your monthly statement is ready",
      "readStatus": true,
      "createdDate": "2026-05-07T11:02:34.000Z"
    }
  ]
}
```

Processing:

- `EbayMessageService.upsert_conversation()` creates/updates the `conversations` row.
- `EbayMessageService.upsert_messages()` creates/updates `messages`.
- If `provider_conversation_type == FROM_EBAY` or sender is `eBay`, message is stored as `MessageSenderType.PROVIDER` and `is_inbound = false`.
- Otherwise, sender matching the account username is `AGENT`; a different sender is `CUSTOMER`.
- New inbound customer messages start an SLA cycle.
- New inbound messages in categorized conversations notify assigned category users.

Database mapping:

| eBay Field | Local Field |
|---|---|
| `conversationId` | `conversations.provider_conversation_id` |
| `conversationTitle` | `conversations.subject` |
| `conversationStatus` | `conversations.provider_conversation_status` |
| `conversationType` | `conversations.provider_conversation_type` |
| `referenceId` | `conversations.reference_id` |
| `referenceType` | `conversations.reference_type` |
| `unreadCount` | `conversations.unread_count` |
| full summary/detail | `conversations.raw_payload` |
| `messageId` | `messages.provider_message_id` |
| `messageBody` | `messages.body` |
| `senderUsername` | `messages.sender_identifier` |
| `recipientUsername` | `messages.recipient_identifier` |
| `readStatus` | `messages.read_status` |
| `createdDate` | `messages.sent_at` |
| full message object | `messages.raw_payload` |

### 5.3 Message Attachments

eBay returns attachments inside message detail payloads. The code accepts several possible keys:

```text
messageMedia
MessageMedia
attachments
messageAttachments
documents
files
```

Response example:

```json
{
  "messageId": "6271234567890",
  "messageBody": "",
  "senderUsername": "buyer123",
  "recipientUsername": "aeliya-ship110",
  "readStatus": true,
  "createdDate": "2026-06-12T09:45:00.000Z",
  "messageMedia": [
    {
      "mediaName": "image001.jpg",
      "mediaUrl": "https://i.ebayimg.com/images/g/example/s-l1600.jpg",
      "mediaType": "IMAGE"
    }
  ]
}
```

Processing:

- `EbayMessageService._attachments_from_message_payload()` normalizes attachment fields.
- `MessageRepository.replace_attachments()` replaces the message attachment set.
- Existing rows with the same `provider_attachment_id` are reused.
- Duplicate attachment IDs in the same sync batch are skipped.

Stored in:

```text
message_attachments.provider_attachment_id
message_attachments.file_name
message_attachments.media_name
message_attachments.media_url
message_attachments.media_type
message_attachments.mime_type
message_attachments.file_size
message_attachments.download_url
message_attachments.raw_payload
```

---

## 6. Product / Listing Context Enrichment

### Where It Starts

During message sync:

```text
EbaySyncService._process_conversation_detail()
  -> ConversationProductContextService.enrich_conversation(conversation)
```

During inbox detail load:

```text
GET /api/v1/conversations/{conversation_id}
  -> ConversationProductContextService.context_for_conversation()
```

### Local First, Browse API Second

The service enriches only when:

```text
conversation.reference_type == LISTING
conversation.reference_id exists
```

It tries:

1. Reuse existing `conversation_product_contexts` for the same conversation/reference.
2. Upgrade from local order line item data if orders have changed.
3. Reuse another cached context for the same account/environment/reference.
4. Call eBay Browse API.

### Browse App Token Request

Uses client credentials, not seller OAuth token.

```http
POST https://api.ebay.com/identity/v1/oauth2/token
Authorization: Basic base64(client_id:client_secret)
Content-Type: application/x-www-form-urlencoded

grant_type=client_credentials&
scope=https://api.ebay.com/oauth/api_scope
```

Response:

```json
{
  "access_token": "v^1.1#i^1#...",
  "expires_in": 7200,
  "token_type": "Application Access Token"
}
```

### Browse Get Item by Legacy ID

Request:

```http
GET https://api.ebay.com/buy/browse/v1/item/get_item_by_legacy_id?legacy_item_id=405955485665
Authorization: Bearer <app_access_token>
Accept: application/json
X-EBAY-C-MARKETPLACE-ID: EBAY_US
```

Response example:

```json
{
  "itemId": "v1|405955485665|0",
  "legacyItemId": "405955485665",
  "title": "E2S A105N Alarm Sounder 24VDC",
  "image": {
    "imageUrl": "https://i.ebayimg.com/images/g/example/s-l1600.jpg"
  },
  "seller": {
    "username": "aeliya-ship110",
    "feedbackPercentage": "99.8",
    "feedbackScore": 12345
  },
  "itemWebUrl": "https://www.ebay.com/itm/405955485665",
  "price": {
    "value": "120.00",
    "currency": "USD"
  },
  "buyingOptions": ["FIXED_PRICE", "BEST_OFFER"]
}
```

Stored in `conversation_product_contexts`:

```text
reference_id
reference_type
item_title
image_url
seller_username
item_url
price_value
price_currency
offer_available
buy_now_available
cta_type
sku
order_id
enrichment_status
raw_payload
last_enriched_at
```

Frontend receives it inside conversation detail:

```json
{
  "product_context": {
    "reference_id": "405955485665",
    "title": "E2S A105N Alarm Sounder 24VDC",
    "image_url": "https://i.ebayimg.com/images/g/example/s-l1600.jpg",
    "seller_username": "aeliya-ship110",
    "item_url": "https://www.ebay.com/itm/405955485665",
    "price": 120.0,
    "currency": "USD",
    "offer_available": true,
    "buy_now_available": true,
    "cta_type": "SEND_OFFER",
    "sku": "SKU-123",
    "order_id": "15-14836-23086",
    "enrichment_status": "ENRICHED"
  }
}
```

---

## 7. eBay Order Sync

### Where It Starts

During full account sync:

```text
EbaySyncService._sync_related_data()
  -> EbayOrderSyncService.sync_account(account.id)
```

Service files:

```text
backend/app/modules/integrations/ebay/services/ebay_order_sync_service.py
backend/app/modules/integrations/ebay/orders/providers.py
backend/app/services/order_context_service.py
backend/app/repositories/order_context_repository.py
```

### eBay Sell Fulfillment Orders API

First sync uses no cursor filter.

```http
GET https://api.ebay.com/sell/fulfillment/v1/order?limit=200&offset=0
Authorization: Bearer <seller_access_token>
Accept: application/json
```

Incremental sync uses `last_order_sync_at` with a 5 minute overlap:

```http
GET https://api.ebay.com/sell/fulfillment/v1/order?limit=200&offset=0&filter=lastmodifieddate:[2026-07-09T04:30:00.000Z..2026-07-09T05:30:00.000Z]
Authorization: Bearer <seller_access_token>
Accept: application/json
```

Response example:

```json
{
  "href": "https://api.ebay.com/sell/fulfillment/v1/order?limit=200&offset=0",
  "total": 2,
  "limit": 200,
  "offset": 0,
  "orders": [
    {
      "orderId": "15-14836-23086",
      "legacyOrderId": "15-14836-23086",
      "creationDate": "2026-07-07T06:20:15.000Z",
      "lastModifiedDate": "2026-07-07T07:37:22.803Z",
      "paymentStatus": "PAID",
      "fulfillmentStatus": "FULFILLED",
      "cancelStatus": "NONE_REQUESTED",
      "buyer": {
        "username": "buyer123"
      },
      "pricingSummary": {
        "priceSubtotal": {
          "value": "120.00",
          "currency": "USD"
        },
        "total": {
          "value": "132.00",
          "currency": "USD"
        }
      },
      "lineItems": [
        {
          "lineItemId": "1001",
          "legacyItemId": "405955479049",
          "sku": "45777",
          "title": "Example industrial item",
          "quantity": 1,
          "lineItemCost": {
            "value": "120.00",
            "currency": "USD"
          },
          "image": {
            "imageUrl": "https://i.ebayimg.com/images/g/example/s-l1600.jpg"
          }
        }
      ]
    }
  ]
}
```

Processing:

- `EbayOrderSyncService._fetch_page_with_retry()` reserves API usage, fetches a page, refreshes token on 401, retries 429/5xx up to 3 times.
- `OrderContextService.upsert_order_payload()` delegates to `OrderContextRepository.upsert_order()`.
- The repository upserts `orders` by `(account_id, order_id)`.
- It clears and recreates `order_line_items` for that order from the latest payload.
- After pages finish, `match_account_conversations()` tries to link all account conversations to synced orders.
- `ebay_accounts.last_order_sync_at` is advanced to sync start time.

Order header mapping:

| eBay Field | Local Field |
|---|---|
| `orderId` | `orders.order_id` |
| `buyer.username` | `orders.buyer_username` |
| `paymentStatus` | `orders.payment_status` |
| `fulfillmentStatus` | `orders.fulfillment_status` |
| `cancelStatus` | `orders.cancel_status` |
| `pricingSummary` | `orders.pricing_summary` |
| `refunds[]` | `orders.refunds` |
| `creationDate` | `orders.external_created_at` |
| `lastModifiedDate` | `orders.external_last_modified_at` |
| full order object | `orders.raw_payload` |

Line item mapping:

| eBay Field | Local Field |
|---|---|
| `lineItemId` | `order_line_items.line_item_id` |
| `itemId` or `legacyItemId` | `order_line_items.item_id` |
| `listingId` or `legacyListingId` | `order_line_items.listing_id` |
| `sku` or `sellerSku` | `order_line_items.sku` |
| `title` | `order_line_items.title` |
| `image.imageUrl` | `order_line_items.image_url` |
| `quantity` | `order_line_items.quantity` |
| `lineItemCost.value` | `order_line_items.price_value` |
| `lineItemCost.currency` | `order_line_items.price_currency` |
| full line item object | `order_line_items.raw_payload` |

### Conversation-to-Order Matching

`OrderContextService.link_conversation_context()` extracts identifiers from:

- `conversation.raw_payload`
- `conversation.raw_payload.summary`
- `conversation.raw_payload.detail`
- `conversation.reference_id` when `reference_type == LISTING`

Matching strategies:

| Strategy | When Used | Confidence |
|---|---|---|
| `DIRECT_ORDER_ID` | Payload contains order ID and direct matching is allowed | `1.0` |
| `BUYER_ITEM_MATCH` | One order matches buyer and item/listing | `0.95` |
| `BUYER_ITEM_DATE_MATCH` | Multiple buyer/item candidates, choose closest to conversation date | `0.85` |
| `BUYER_NEARBY_ORDER` | One buyer order near conversation date | `0.60` |
| `BUYER_NEARBY_DATE_MATCH` | Multiple nearby buyer orders, choose closest | `0.50` |
| `NO_MATCH` | No candidate found | `0.0` |
| `MANUAL` | User selected an order in the UI | calculated in response |

Stored in `conversation_order_contexts`:

```text
conversation_id
order_record_id
ebay_order_id
legacy_order_id
ebay_item_id
listing_id
transaction_id
external_message_id
sku
title
image_url
buyer_username
inventory_id
match_strategy
confidence_score
raw_identifiers
sync_timestamp
```

Frontend can manually select an order:

```http
PATCH /api/v1/conversations/{conversation_id}/order
Content-Type: application/json

{
  "order_record_id": "uuid-or-null"
}
```

---

## 8. Offer Sync and Offer Cards

Offers are intentionally separated from ordinary message storage.

Important rule:

```text
FROM_EBAY conversations are stored and displayed as eBay/system messages.
FROM_EBAY conversations are not used to create offer cards.
Offer cards are linked only to normal FROM_MEMBERS conversations.
```

### Offer Sources

| Source | API / Logic | Service | Purpose |
|---|---|---|---|
| Buyer Best Offers | Trading API `GetBestOffers` | `EbayBestOfferSyncService` | Sync active buyer-originated offers |
| Seller offer notifications | Trading API `GetMyMessages` | `EbaySellerOfferSyncService` | Read seller/system offer notification headers |
| Conversation text resolver | Local parsing on conversation open | `EbayConversationOfferResolver` | Attach or create offers from stored member messages |
| Local read API | Local database | `EbayNegotiationService` | Return offers for conversation |

### 8.1 Trading API GetBestOffers

Request:

```http
POST https://api.ebay.com/ws/api.dll
X-EBAY-API-CALL-NAME: GetBestOffers
X-EBAY-API-SITEID: 0
X-EBAY-API-COMPATIBILITY-LEVEL: 1455
X-EBAY-API-IAF-TOKEN: <seller_access_token>
Content-Type: text/xml

<?xml version="1.0" encoding="utf-8"?>
<GetBestOffersRequest xmlns="urn:ebay:apis:eBLBaseComponents">
  <DetailLevel>ReturnAll</DetailLevel>
  <BestOfferStatus>Active</BestOfferStatus>
  <Pagination>
    <EntriesPerPage>200</EntriesPerPage>
    <PageNumber>1</PageNumber>
  </Pagination>
</GetBestOffersRequest>
```

The XML is parsed into normalized JSON:

```json
{
  "ack": "Success",
  "totalPages": 1,
  "error": null,
  "offers": [
    {
      "offerId": "9988776655",
      "listingId": "405955485665",
      "buyerUsername": "buyer123",
      "buyerMessage": "Can you do 45?",
      "sellerMessage": null,
      "expirationTime": "2026-06-14T05:47:00.000Z",
      "amount": "45.00",
      "currency": "USD",
      "quantity": "1",
      "status": "Active",
      "offerType": "BestOffer"
    }
  ]
}
```

Processing:

- Match conversation by `(reference_id/listing_id, buyer_identifier)`, then by buyer fallback.
- If matched conversation is `FROM_EBAY`, save offer without conversation link.
- Upsert `offers` by `(provider, account_id, provider_offer_id)`.
- Status mapping:

```text
ACTIVE, PENDING -> PENDING
ACCEPTED        -> ACCEPTED
DECLINED        -> DECLINED
EXPIRED         -> EXPIRED
```

Stored in:

| Normalized Field | Local Field |
|---|---|
| `offerId` | `offers.provider_offer_id` |
| `listingId` | `offers.listing_id` |
| `buyerUsername` | `offers.buyer_username` |
| `amount` | `offers.offer_amount` |
| `currency` | `offers.currency` |
| `status` | `offers.status` |
| incoming buyer offer | `offers.direction = INCOMING` |
| `offerType` | `offers.offer_type` |
| `quantity` | `offers.quantity` |
| `buyerMessage` | `offers.raw_text` |
| `expirationTime` | `offers.expires_at` |
| full parsed object | `offers.raw_payload` |

### 8.2 Trading API GetMyMessages

Used for seller/system offer notification headers.

Request:

```http
POST https://api.ebay.com/ws/api.dll
X-EBAY-API-CALL-NAME: GetMyMessages
X-EBAY-API-SITEID: 0
X-EBAY-API-COMPATIBILITY-LEVEL: 1455
X-EBAY-API-IAF-TOKEN: <seller_access_token>
Content-Type: text/xml

<?xml version="1.0" encoding="utf-8"?>
<GetMyMessagesRequest xmlns="urn:ebay:apis:eBLBaseComponents">
  <DetailLevel>ReturnHeaders</DetailLevel>
  <Pagination>
    <EntriesPerPage>200</EntriesPerPage>
    <PageNumber>1</PageNumber>
  </Pagination>
</GetMyMessagesRequest>
```

The XML is parsed into:

```json
{
  "ack": "Success",
  "total_pages": 1,
  "error": null,
  "messages": [
    {
      "message_id": "1234567890",
      "subject": "Counteroffer submitted to buyer: US $43.41 for OMRON relay (405955485665)",
      "body": null,
      "sender": "eBay",
      "recipient": "aeliya-ship110",
      "message_type": "AskSellerQuestion",
      "sent_date": "2026-06-12T05:47:00.000Z",
      "receive_date": "2026-06-12T05:47:05.000Z",
      "item_id": "405955485665",
      "message_status": "Read",
      "read": true,
      "flagged": false
    }
  ]
}
```

Processing:

- Check subject for offer phrases such as:

```text
accepted an offer
accepted your offer
counteroffer submitted to buyer
you have a new offer
buyer made a counteroffer
best offer
sent an offer
```

- Parse amount/currency/item/buyer/type from the subject.
- Match to a non-`FROM_EBAY` conversation by item ID and/or buyer.
- Create/update a local `messages` row with `sender_type = SYSTEM`.
- Create/update an `offers` row.

Example parsed offer:

```json
{
  "provider_offer_id": "1234567890",
  "listing_id": "405955485665",
  "buyer_username": "buyer123",
  "offer_amount": "43.41",
  "currency": "USD",
  "status": "PENDING",
  "direction": "OUTGOING",
  "offer_type": "SELLER_COUNTEROFFER",
  "raw_text": "Counteroffer submitted to buyer: US $43.41 for OMRON relay (405955485665)"
}
```

### 8.3 On-Demand Conversation Offer Resolver

Service:

```text
backend/app/modules/integrations/ebay/services/ebay_conversation_offer_resolver.py
```

This resolver is for normal member conversations. It:

- exits immediately for `FROM_EBAY`
- clears `message.offer_data` for system conversations
- attaches already synced offers by listing ID and buyer
- parses stored messages for known offer phrases
- upserts offers and links them to exact `message_id`
- writes `message.offer_data` for UI convenience

Supported phrases include:

```text
buyer sent an offer
you have a new offer
sent an offer
you sent an offer
you sent a counteroffer
buyer made a counteroffer
accepted an offer
offer accepted
offer expired
offer declined
```

Offer card response shape:

```json
{
  "id": "offer-uuid",
  "provider_offer_id": "6270000000019",
  "listing_id": "405955485665",
  "buyer_username": "buyer123",
  "offer_amount": "45.00",
  "currency": "USD",
  "status": "PENDING",
  "direction": "INCOMING",
  "offer_type": "BUYER_OFFER",
  "message": null,
  "raw_text": "buyer123 sent an offer $45.00",
  "expires_at": null,
  "created_at": "2026-06-12T05:47:00Z"
}
```

Frontend rule:

```text
Render offer cards from backend-provided offers.
Do not parse message body in the frontend to invent offers.
```

---

## 9. Inbox and Conversation Module Flow

### Conversation List

Frontend:

```text
Dashboard.loadConversations()
  -> fetchConversations()
  -> GET /api/v1/conversations
```

Backend:

```text
ConversationService.list_conversations()
ConversationRepository.list()
```

Query filters:

```text
limit
offset
search
status
provider
conversation_type
ebay_account_id
assigned_user_id
category_id
```

Agent visibility:

- Admin and operations manager see unrestricted data.
- Support agents see conversations in assigned categories plus directly assigned conversations.

Response example:

```json
{
  "items": [
    {
      "id": "conversation-uuid",
      "provider": "EBAY",
      "provider_conversation_id": "208491463945",
      "provider_account_id": "account-uuid",
      "subject": "Question about item 405955487848",
      "buyer_identifier": "buyer123",
      "provider_conversation_type": "FROM_MEMBERS",
      "reference_id": "405955487848",
      "reference_type": "LISTING",
      "unread_count": 1,
      "message_count": 2,
      "last_message_preview": "Available?",
      "last_message_direction": "Customer",
      "calculated_status": "OPEN",
      "is_not_read": true,
      "is_replied": false,
      "response_due_at": "2026-07-09T12:30:00Z",
      "category": {
        "id": "category-uuid",
        "name": "Product Inquiry",
        "color": "#2563eb"
      },
      "seller_account": {
        "id": "account-uuid",
        "account_name": "Aeliya Ship",
        "ebay_username": "aeliya-ship110",
        "store_name": "Aeliya Marine"
      }
    }
  ],
  "total": 1,
  "limit": 20,
  "offset": 0
}
```

### Conversation Detail

Frontend:

```text
Dashboard.loadConversationDetail()
  -> fetchConversation(conversationId)
  -> GET /api/v1/conversations/{conversation_id}
```

Backend flow:

```text
ConversationService.get_conversation()
if not-read -> mark_read()
ConversationProductContextService.context_for_conversation()
OrderContextService.build_context()
MessageTypeDetectionService.suggest()
serialize_conversation()
```

Response example:

```json
{
  "id": "conversation-uuid",
  "provider": "EBAY",
  "provider_conversation_id": "208491463945",
  "provider_account_id": "account-uuid",
  "subject": "Question about item 405955487848",
  "buyer_identifier": "buyer123",
  "provider_conversation_type": "FROM_MEMBERS",
  "reference_id": "405955487848",
  "reference_type": "LISTING",
  "message_count": 2,
  "status": "OPEN",
  "messages": [
    {
      "id": "message-uuid-1",
      "provider": "EBAY",
      "provider_message_id": "6275165199019",
      "sender_type": "CUSTOMER",
      "sender_identifier": "buyer123",
      "recipient_identifier": "aeliya-ship110",
      "body": "Available?",
      "read_status": true,
      "is_inbound": true,
      "sent_at": "2026-06-16T21:08:23Z",
      "attachments": []
    }
  ],
  "offers": [],
  "assignments": [],
  "notes": [],
  "product_context": {
    "reference_id": "405955487848",
    "title": "Example industrial item",
    "image_url": "https://i.ebayimg.com/images/g/example/s-l1600.jpg",
    "price": 120.0,
    "currency": "USD",
    "enrichment_status": "ENRICHED"
  },
  "order_context": {
    "selected_order": {
      "id": "order-record-uuid",
      "order_id": "15-14836-23086",
      "buyer_username": "buyer123",
      "payment_status": "PAID",
      "fulfillment_status": "FULFILLED",
      "line_items": []
    },
    "candidate_orders": [],
    "linking": {
      "strategy": "BUYER_ITEM_MATCH",
      "requires_manual_selection": false
    },
    "deep_links": {}
  },
  "suggested_message_type_id": "message-type-uuid"
}
```

---

## 10. Reply Flow

### Where It Starts

Frontend:

- `ReplyComposer`
- `sendConversationReply()`
- `sendConversationReplyWithAttachments()`

Backend:

```http
POST /api/v1/conversations/{conversation_id}/reply/validate
POST /api/v1/conversations/{conversation_id}/reply
```

Service:

```text
backend/app/services/ebay_reply_service.py
```

### Rules Before Sending

The backend rejects replies when:

- body is empty or over 2000 characters
- no active leaf message type was selected
- conversation is closed
- conversation is not eBay
- conversation is `FROM_EBAY`
- conversation has no eBay account
- current user is trying to reply to a conversation assigned to someone else
- eBay reply policy validation fails

### With No Attachments

Flow:

```text
validate body and message type
load conversation and account
refresh access token if needed
create pending local Message row
call eBay send_message API
replace pending provider_message_id with eBay messageId
update conversation.last_message_at
complete SLA cycle
create message classification
write audit logs
commit
```

### With Attachments

Flow:

```text
validate uploads
store attachment metadata/files locally
upload each image to eBay Media API
build messageMedia[] from eBay-hosted mediaUrl values
send eBay message with messageMedia[]
mark local attachments as ebay_sent
commit
```

If any upload or send fails, the transaction is rolled back. There is no text-only fallback.

### eBay Media API

Request:

```http
POST https://apim.ebay.com/commerce/media/v1_beta/image/create_image_from_file
Authorization: Bearer <seller_access_token>
Accept: application/json
Content-Type: multipart/form-data
```

Response example:

```json
{
  "imageUrl": "https://i.ebayimg.com/images/g/example/s-l1600.jpg",
  "maxDimensionImageUrl": "https://i.ebayimg.com/images/g/example/s-l1600.jpg"
}
```

The code also handles a `Location` header by performing a follow-up GET if eBay returns the image resource URL instead of `imageUrl` directly.

### eBay Send Message API

Request:

```http
POST https://api.ebay.com/commerce/message/v1/send_message
Authorization: Bearer <seller_access_token>
Accept: application/json
Content-Type: application/json

{
  "conversationId": "208491463945",
  "conversationType": "FROM_MEMBERS",
  "messageText": "Yes, this item is available.",
  "messageMedia": [
    {
      "mediaName": "photo.jpg",
      "mediaUrl": "https://i.ebayimg.com/images/g/example/s-l1600.jpg"
    }
  ]
}
```

Response example:

```json
{
  "messageId": "3497560590099"
}
```

Stored in local `messages`:

```text
sender_type = AGENT
sender_identifier = ebay_accounts.ebay_username
recipient_identifier = conversations.buyer_identifier
is_inbound = false
read_status = true
provider_message_id = response.messageId
raw_payload = eBay response + actor_id
```

---

## 11. Categorization, Assignment, SLA, and Notifications

### Categories

Frontend:

- `frontend/src/pages/categories.jsx`

Backend:

- `backend/app/api/v1/routes/categories.py`
- `backend/app/services/categorization_service.py`

During sync, `EbayMessageService.upsert_conversation()` builds classification text from:

```text
subject
buyer_identifier
reference_id
message bodies
```

If `CategorizationService.classify_text()` returns a category and the conversation was not manually categorized, the conversation category is updated.

Manual category updates:

```http
PATCH /api/v1/conversations/{conversation_id}/category
```

Manual categories set `category_manually_selected` so later syncs do not overwrite the user choice.

### Assignment

Frontend:

- dashboard assignment controls
- bulk assignment bar

Backend:

```http
POST /api/v1/conversations/{conversation_id}/assign
POST /api/v1/conversations/bulk-update
```

Stored in:

```text
conversation_assignments
```

Assignment rules:

- Admin, operations manager, and support agent can assign.
- Users cannot reply to a thread assigned to someone else.
- Closed conversations cannot be reassigned.

### SLA

Backend:

- `backend/app/services/sla_service.py`

Flow:

- New inbound customer message starts an SLA cycle.
- Successful outbound eBay reply completes the active cycle.
- Each cycle is stored in `conversation_sla_history`.

Stored fields:

```text
conversation_id
cycle_number
buyer_message_time
replied_time
replied_by
response_duration_seconds
sla_met
```

### Notifications

Backend:

- `backend/app/services/notification_service.py`
- `backend/app/api/v1/routes/notifications.py`

Created when:

- a new inbound categorized message arrives
- a conversation is assigned

Frontend reads:

```http
GET /api/v1/notifications
PATCH /api/v1/notifications/read
PATCH /api/v1/notifications/{notification_id}/read
```

---

## 12. Message Types and Reports

Message types are selected when an agent replies. They are used for reporting and analytics.

Frontend:

```text
frontend/src/pages/message_types.jsx
frontend/src/pages/message_reports.jsx
frontend/src/components/conversations/ReplyComposer.jsx
```

Backend:

```text
backend/app/api/v1/routes/message_types.py
backend/app/models/message_type.py
backend/app/repositories/message_type_repository.py
```

Reply flow:

```text
agent selects a leaf message type
EbayReplyService validates it
reply is sent
MessageClassificationRepository.create() stores the classification
reports aggregate classifications by date/account/user/category/type
```

Report endpoints:

```http
GET /api/v1/reports/message-types
GET /api/v1/reports/message-types/export
```

---

## 13. Analytics and Audit Logs

### Analytics

Frontend:

- `frontend/src/pages/analytics.jsx`

Backend:

- `backend/app/api/v1/routes/analytics.py`
- `backend/app/services/analytics_service.py`

Endpoints:

```http
GET /api/v1/analytics/dashboard
GET /api/v1/analytics/dashboard/export
```

Typical dashboard metrics include conversation volume, status distribution, assignment/category dimensions, and response performance from stored local data.

### Audit Logs

Frontend:

- `frontend/src/pages/audit_logs.jsx`

Backend:

- `backend/app/api/v1/routes/audit_logs.py`
- `backend/app/services/audit_service.py`

Logged actions include:

```text
EBAY_ACCOUNT_CREATED
EBAY_ACCOUNT_UPDATED
EBAY_ACCOUNT_ACTIVATED
EBAY_ACCOUNT_DEACTIVATED
EBAY_ACCOUNT_DELETED
EBAY_CONNECT_LINK_GENERATED
EBAY_MANUAL_CALLBACK_SUBMITTED
CONVERSATION_ASSIGNED
MESSAGE_STATUS_CHANGED
MESSAGE_CATEGORY_CHANGED
BULK_ASSIGNMENT_UPDATED
MESSAGE_REPLY_SENT
REPLY_CATEGORIZED
```

Endpoints:

```http
GET /api/v1/audit-logs
GET /api/v1/audit-logs/export
```

---

## 14. API-to-Database Summary

| Source | External API | Response Root | Main Local Tables |
|---|---|---|---|
| OAuth token exchange | `POST /identity/v1/oauth2/token` | token object | `ebay_accounts` |
| Seller identity | `GET /commerce/identity/v1/user/` | user object | `ebay_accounts` |
| Conversation list | `GET /commerce/message/v1/conversation` | `conversations[]` | `conversations.raw_payload.summary` |
| Conversation detail | `GET /commerce/message/v1/conversation/{id}` | `messages[]` | `conversations`, `messages`, `message_attachments` |
| Browse item | `GET /buy/browse/v1/item/get_item_by_legacy_id` | item object | `conversation_product_contexts` |
| Orders | `GET /sell/fulfillment/v1/order` | `orders[]` | `orders`, `order_line_items`, `conversation_order_contexts` |
| Buyer offers | Trading API `GetBestOffers` | parsed `offers[]` | `offers` |
| Seller offer notifications | Trading API `GetMyMessages` | parsed `messages[]` | `messages`, `offers` |
| Media upload | `POST /commerce/media/v1_beta/image/create_image_from_file` | image object/location | `message_attachments.raw_payload` |
| Send reply | `POST /commerce/message/v1/send_message` | message ID object | `messages`, `conversation_sla_history`, `audit_logs` |

---

## 15. Environment Variables

Configured in `backend/.env` via `backend/app/core/config.py`.

```env
DATABASE_URL=postgresql+psycopg://user:password@localhost:5432/aces
SECRET_KEY=change-me
ACCESS_TOKEN_EXPIRE_MINUTES=15
REFRESH_TOKEN_EXPIRE_DAYS=30
FRONTEND_URL=http://localhost:5173
BACKEND_CORS_ORIGINS=http://localhost:5173,http://127.0.0.1:5173

EBAY_CLIENT_ID=your-client-id
EBAY_CLIENT_SECRET=your-client-secret
EBAY_REDIRECT_URI=http://localhost:8000/api/v1/integrations/ebay/callback
EBAY_RUNAME=your-ebay-runame
EBAY_ENVIRONMENT=SANDBOX
EBAY_MARKETPLACE_ID=EBAY_US
EBAY_DAILY_API_LIMIT=100
EBAY_BROWSE_MAX_RETRIES=3
EBAY_BROWSE_RETRY_BASE_SECONDS=0.5

SMTP_HOST=
SMTP_PORT=587
SMTP_USERNAME=
SMTP_PASSWORD=
SMTP_FROM_EMAIL=
SMTP_USE_TLS=true

PUBLIC_BACKEND_URL=
REPLY_ATTACHMENT_MAX_BYTES=5242880
REPLY_ATTACHMENT_UPLOAD_DIR=uploads/reply_attachments

TRANSLATION_API_URL=
TRANSLATION_API_KEY=
```

---

## 16. Local Development

### Backend

```bash
cd backend
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
alembic upgrade head
uvicorn app.main:app --reload
```

Backend health check:

```http
GET http://localhost:8000/health
```

Expected:

```json
{
  "status": "ok"
}
```

### Frontend

```bash
cd frontend
npm install
npm run dev
```

Default frontend URL:

```text
http://localhost:5173
```

---

## 17. Important Known Behaviors

- The message sync fetches conversation detail with `limit=50`. If eBay returns more than 50 messages for a single conversation, this code does not currently paginate message detail pages.
- Full sync calls both `FROM_MEMBERS` and `FROM_EBAY`.
- `FROM_EBAY` conversations are displayed but are not replyable and are skipped for offer-card extraction.
- Order sync is non-fatal inside full message sync. If order sync fails, message sync can still complete as `SUCCESS_WITH_ERRORS`.
- BestOffer sync and seller-offer sync are also non-fatal inside full sync.
- Product enrichment may use local order data instead of Browse API when available.
- Reply attachments are uploaded to eBay first. If eBay media upload fails, the reply is not sent.
- Existing user changes in category/status/assignment are not overwritten by normal sync except for provider fields that mirror eBay state.
