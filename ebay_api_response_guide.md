# eBay API Response Guide for Helpdesk Sync

This document explains the eBay APIs used in the Helpdesk sync flow, what each API returns, what the response shape looks like, and examples of the payloads.

The goal is to make it clear which API is responsible for:

- fetching eBay conversations
- fetching eBay conversation messages
- syncing eBay orders
- fetching product/listing context
- syncing best offers
- reading seller offer notifications from My Messages
- storing the final data in local database models

---

## 1. Overall Sync Flow

The main sync service processes both eBay conversation types:

```text
FROM_MEMBERS
FROM_EBAY
```

The backend flow is:

```text
Sync eBay account
  ↓
Fetch conversation list pages for FROM_MEMBERS and FROM_EBAY
  ↓
For each conversation summary, fetch conversation detail
  ↓
Upsert conversation
  ↓
Upsert messages
  ↓
Store attachments
  ↓
For non-FROM_EBAY conversations only, detect simple eBay-style offer event messages
  ↓
Store offer rows linked to the exact message and conversation
  ↓
Sync order context
  ↓
Sync Best Offers where available
  ↓
Return conversations/messages/offers to frontend
```

Important rule:

```text
FROM_EBAY messages are stored and displayed as normal eBay/system messages.
FROM_EBAY messages are not used for offer extraction.
Offer extraction runs only for conversationType != FROM_EBAY.
```

---

## 2. eBay Commerce Message API — Conversation List

### Purpose

Fetches a paginated list of eBay conversations for a given conversation type.

Used for:

- discovering conversation IDs
- reading conversation title/status/type
- reading listing reference IDs where available
- deciding which conversation detail API call to make next

### Endpoint Shape

```http
GET https://api.ebay.com/commerce/message/v1/conversation?conversation_type={FROM_MEMBERS|FROM_EBAY}&limit=50&offset=0
Authorization: Bearer <access_token>
Accept: application/json
```

### Query Parameters

| Parameter | Meaning |
|---|---|
| `conversation_type` | `FROM_MEMBERS` or `FROM_EBAY` |
| `limit` | Page size, commonly `50` |
| `offset` | Pagination offset |

### Response Shape

```json
{
  "limit": 50,
  "offset": 150,
  "total": 918,
  "href": "https://api.ebay.com/commerce/message/v1/conversation?conversation_type=FROM_EBAY&offset=150&limit=50",
  "prev": "https://api.ebay.com/commerce/message/v1/conversation?conversation_type=FROM_EBAY&offset=100&limit=50",
  "next": "https://api.ebay.com/commerce/message/v1/conversation?conversation_type=FROM_EBAY&offset=200&limit=50",
  "conversations": [
    {
      "conversationId": "208491463945",
      "conversationStatus": "ACTIVE",
      "conversationTitle": "You have a new offer: US $75.00 for CISCO GLC-LX-SM-RGD ... (405955487848)",
      "conversationType": "FROM_EBAY",
      "createdDate": "2026-05-06T20:42:08.000Z",
      "referenceId": "405955487848",
      "referenceType": "LISTING",
      "unreadCount": 0
    }
  ]
}
```

### Important Fields

| Field | Meaning | Local Storage Target |
|---|---|---|
| `conversationId` | eBay conversation ID | `conversations.provider_conversation_id` |
| `conversationStatus` | eBay status such as `ACTIVE` | `conversations.provider_conversation_status` |
| `conversationTitle` | Conversation subject/title | `conversations.subject` |
| `conversationType` | `FROM_MEMBERS` / `FROM_EBAY` | `conversations.provider_conversation_type` |
| `createdDate` | eBay created timestamp | `conversations.external_created_at` |
| `referenceId` | Usually listing/item ID when available | `conversations.reference_id` |
| `referenceType` | Usually `LISTING` | `conversations.reference_type` |
| `unreadCount` | eBay unread count | `conversations.unread_count` |

### Notes

- `FROM_MEMBERS` conversations are buyer/seller message threads.
- `FROM_EBAY` conversations are eBay system/provider messages.
- Both types are fetched by the sync service.
- The offer extraction service must skip `FROM_EBAY`.

---

## 3. eBay Commerce Message API — Conversation Detail

### Purpose

Fetches the full message list for one eBay conversation.

Used for:

- storing individual messages
- reading message bodies
- reading sender/recipient usernames
- reading message timestamps
- reading attachments/media
- detecting simple eBay-style offer event messages for non-`FROM_EBAY` conversations

### Endpoint Shape

```http
GET https://api.ebay.com/commerce/message/v1/conversation/{conversationId}?conversation_type={FROM_MEMBERS|FROM_EBAY}&limit=50&offset=0
Authorization: Bearer <access_token>
Accept: application/json
```

### Response Shape — FROM_MEMBERS Example

```json
{
  "limit": 50,
  "offset": 0,
  "total": 3,
  "href": "https://api.ebay.com/commerce/message/v1/conversation/125432475305?conversation_type=FROM_MEMBERS&offset=0&limit=50",
  "conversationTitle": "Dear ibrkha-3737, We already have responded to your query...",
  "conversationStatus": "ACTIVE",
  "conversationType": "FROM_MEMBERS",
  "messages": [
    {
      "messageId": "3497560590015",
      "messageBody": "Dear ibrkha-3737,\n\nWe already have responded to your query from our other eBay Account...",
      "senderUsername": "aeliya-ship110",
      "recipientUsername": "ibrkha-3737",
      "readStatus": true,
      "createdDate": "2026-06-17T06:49:32.000Z"
    },
    {
      "messageId": "6275165199019",
      "messageBody": "Available?",
      "senderUsername": "ibrkha-3737",
      "recipientUsername": "aeliya-ship110",
      "readStatus": true,
      "createdDate": "2026-06-16T21:08:23.000Z"
    }
  ]
}
```

### Response Shape — FROM_EBAY Example

```json
{
  "limit": 50,
  "offset": 0,
  "total": 1,
  "href": "https://api.ebay.com/commerce/message/v1/conversation/208519361635?conversation_type=FROM_EBAY&offset=0&limit=50",
  "conversationTitle": "Your April full statement is ready",
  "conversationStatus": "ACTIVE",
  "conversationType": "FROM_EBAY",
  "messages": [
    {
      "messageId": "208519361635",
      "messageBody": "<!DOCTYPE html><html>...full eBay HTML email body...</html>",
      "senderUsername": "eBay",
      "recipientUsername": "aeliya-ship110",
      "subject": "Your April full statement is ready",
      "readStatus": true,
      "createdDate": "2026-05-07T11:02:34.000Z"
    }
  ]
}
```

### Important Message Fields

| Field | Meaning | Local Storage Target |
|---|---|---|
| `messageId` | eBay message ID | `messages.provider_message_id` |
| `messageBody` | Plain text or HTML body | `messages.body` |
| `senderUsername` | Sender username | `messages.sender_identifier` |
| `recipientUsername` | Recipient username | `messages.recipient_identifier` |
| `subject` | Subject, mostly present for system messages | `messages.raw_payload.subject` or message subject field if present |
| `readStatus` | eBay read boolean | `messages.read_status` |
| `createdDate` | eBay message timestamp | `messages.sent_at` |
| `messageMedia[]` | Attachments/images | `message_attachments` |

### Local Sender Mapping

```text
senderUsername == account.ebay_username
  => sender_type = AGENT
  => is_inbound = false

senderUsername != account.ebay_username
  => sender_type = CUSTOMER, unless senderUsername is eBay/system
  => is_inbound = true

senderUsername == eBay
  => provider/system message display behavior
```

### Offer Extraction Rule

Only after message storage:

```python
if conversation_type == "FROM_EBAY":
    skip_offer_extraction()
else:
    parse_simple_offer_event_message()
```

---

## 4. eBay Message Attachments / `messageMedia[]`

### Purpose

Some eBay messages include images or other media. These are returned inside the conversation detail message payload.

### Response Shape

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
      "mediaUrl": "https://i.ebayimg.com/.../image001.jpg",
      "mediaType": "IMAGE"
    }
  ]
}
```

### Local Mapping

| eBay Field | Local Field |
|---|---|
| `mediaName` | `message_attachments.file_name` / `media_name` |
| `mediaUrl` | `message_attachments.media_url` / `download_url` |
| `mediaType` | `message_attachments.media_type` |
| raw object | `message_attachments.raw_payload` |

### Important Note

A message can have no `messageBody` but still have `messageMedia`. The backend must store both the message and its attachments without crashing.

---

## 5. eBay Trading API — GetMyMessages / Seller Offer Notification Headers

### Purpose

This service calls the older Trading API message endpoint through an internal method named `get_my_messages_raw()`.

Used for:

- fetching seller account message headers
- reading message `subject`
- checking offer-like subjects
- matching them back to stored conversations

Current implementation should skip `FROM_EBAY` and eBay system payloads for offer creation.

### Internal Call Shape

```python
response = client.get_my_messages_raw(
    access_token,
    page_number=page,
    entries_per_page=200,
    detail_level="ReturnHeaders"
)
```

### Normalized Response Shape Expected by Service

```json
{
  "messages": [
    {
      "messageId": "1234567890",
      "subject": "You sent a counteroffer $63.88",
      "senderUsername": "aeliya-ship110",
      "recipientUsername": "buyer123",
      "sent_date": "2026-06-12T05:47:00.000Z",
      "item_id": "405955485665",
      "buyerUsername": "buyer123"
    }
  ],
  "pageNumber": 1,
  "totalPages": 3
}
```

### Local Processing Output

When a valid non-`FROM_EBAY` offer event is detected, the system creates/updates:

1. A local `messages` row if needed.
2. A local `offers` row linked to the message.

### Offer Event Example

Input subject:

```text
You sent a counteroffer $63.88
```

Extracted offer:

```json
{
  "offer_type": "SELLER_COUNTEROFFER",
  "direction": "OUTGOING",
  "status": "PENDING",
  "amount": "63.88",
  "currency": "USD"
}
```

---

## 6. eBay Trading API — GetBestOffers

### Purpose

Fetches buyer-originated Best Offer data from eBay.

Used for:

- syncing buyer offers from eBay Trading API
- materializing offers into the local `offers` table
- linking offers to matching non-`FROM_EBAY` conversations

### Internal Call Shape

```python
response = client.get_best_offers_raw(access_token, page=page)
```

### Expected Response Shape

```json
{
  "offers": [
    {
      "offerId": "9988776655",
      "listingId": "405955485665",
      "buyerUsername": "ricus-i8csgkrp",
      "amount": "45.00",
      "currency": "USD",
      "status": "ACTIVE",
      "offerType": "BEST_OFFER",
      "quantity": 1,
      "buyerMessage": "",
      "createdDate": "2026-06-12T05:47:00.000Z",
      "expirationTime": "2026-06-14T05:47:00.000Z"
    }
  ],
  "page": 1,
  "totalPages": 1
}
```

### Local Offer Mapping

| API Field | Local Offer Field |
|---|---|
| `offerId` | `offers.provider_offer_id` |
| `listingId` | `offers.listing_id` / `reference_id` |
| `buyerUsername` | `offers.buyer_username` |
| `amount` | `offers.offer_amount` |
| `currency` | `offers.currency` |
| `status` | `offers.status` |
| `offerType` | `offers.offer_type` |
| `quantity` | `offers.quantity` |
| `buyerMessage` | `offers.message` / `raw_text` |
| `createdDate` | `offers.created_at_provider` |
| `expirationTime` | `offers.expires_at` |
| full raw object | `offers.raw_payload` |

### Status Mapping

```text
ACTIVE  -> PENDING
PENDING -> PENDING
ACCEPTED -> ACCEPTED
DECLINED -> DECLINED
EXPIRED -> EXPIRED
```

### Important Business Rule

If the matching conversation is `FROM_EBAY`, skip linking/creating the offer card for that conversation. Offers must only be shown in normal member conversations.

---

## 7. eBay Sell Fulfillment API — Orders

### Purpose

Fetches eBay orders for the seller account.

Used for:

- syncing order data
- linking order context to conversations
- matching buyer/item context

### Endpoint Shape

```http
GET https://api.ebay.com/sell/fulfillment/v1/order?limit=200&offset=0&filter=lastmodifieddate:[2026-07-07T06:05:36.000Z..2026-07-07T07:37:22.000Z]
Authorization: Bearer <access_token>
Accept: application/json
```

### Response Shape

```json
{
  "href": "https://api.ebay.com/sell/fulfillment/v1/order?limit=200&offset=0&filter=...",
  "total": 2,
  "limit": 200,
  "offset": 0,
  "orders": [
    {
      "orderId": "15-14836-23086",
      "legacyOrderId": "15-14836-23086",
      "creationDate": "2026-07-07T06:20:15.000Z",
      "lastModifiedDate": "2026-07-07T07:37:22.803Z",
      "orderFulfillmentStatus": "FULFILLED",
      "orderPaymentStatus": "PAID",
      "buyer": {
        "username": "buyer123"
      },
      "pricingSummary": {
        "priceSubtotal": {
          "value": "120.00",
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
          }
        }
      ]
    }
  ]
}
```

### Important Fields

| Field | Meaning |
|---|---|
| `total` | Number of orders matching query |
| `orders[]` | List of order objects |
| `orderId` | eBay order ID |
| `buyer.username` | Buyer username used for conversation matching |
| `lineItems[].legacyItemId` | Item/listing ID used for product/conversation matching |
| `lineItems[].sku` | Seller SKU |
| `lineItems[].title` | Item title |
| `lineItems[].quantity` | Purchased quantity |
| `pricingSummary` | Order-level price info |

### Local Usage

Order sync links conversations using strategies such as:

```text
BUYER_ITEM_MATCH
BUYER_NEARBY_ORDER
```

The order sync result can log:

```json
{
  "orders_processed": 2,
  "orders_failed": 0,
  "pages_processed": 1,
  "conversations_matched": 4
}
```

---

## 8. eBay Browse API — Product / Listing Context

### Purpose

Fetches listing/product context for a conversation reference ID.

Used for:

- showing product title
- showing product image
- showing seller/listing context
- enriching the conversation detail sidebar/banner

### Endpoint Shape

The code/logs show a product context enrichment step using the conversation `reference_id`. The exact internal client method is not shown in the uploaded snippets, but the behavior is:

```text
reference_id from conversation -> Browse API lookup -> title/image/seller fetched
```

### Expected Response Shape

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
  }
}
```

### Local Usage

The product context enrichment can store/display:

| API Field | Local/UI Usage |
|---|---|
| `legacyItemId` | Match to `conversation.reference_id` |
| `title` | Product title in conversation banner/sidebar |
| `image.imageUrl` | Product thumbnail |
| `seller.username` | Seller context |
| `itemWebUrl` | Product link |
| `price` | Optional listing price context |

---

## 9. Local Backend API — Conversation Detail Response

### Purpose

This is the response the frontend should use to display:

- conversation header
- messages
- attachments
- offer cards linked to messages
- side context

The frontend must not parse message text for offers. It should only render `offers[]` returned by the backend.

### Preferred Response Shape

```json
{
  "conversation": {
    "id": "conversation-id",
    "provider": "EBAY",
    "provider_conversation_id": "125869114708",
    "provider_conversation_type": "FROM_MEMBERS",
    "subject": "ENDED - IDEC RH2B-UTDC24V Relay, 10A 240VAC, 7.5A 120VAC",
    "buyer_identifier": "ricus-i8csgkrp",
    "seller_identifier": "aeliya-ship110",
    "reference_id": "405955485665",
    "reference_type": "LISTING",
    "last_message_at": "2026-06-12T09:45:00.000Z"
  },
  "messages": [
    {
      "id": "message-id-1",
      "provider": "EBAY",
      "provider_message_id": "6270000000019",
      "sender_type": "CUSTOMER",
      "sender_identifier": "ricus-i8csgkrp",
      "recipient_identifier": "aeliya-ship110",
      "body": "ricus-i8csgkrp sent an offer $45.00",
      "read_status": true,
      "is_inbound": true,
      "sent_at": "2026-06-12T05:47:00.000Z",
      "attachments": [],
      "offers": [
        {
          "id": "offer-id-1",
          "message_id": "message-id-1",
          "conversation_id": "conversation-id",
          "offer_type": "BUYER_OFFER",
          "direction": "INCOMING",
          "status": "PENDING",
          "amount": "45.00",
          "offer_amount": "45.00",
          "currency": "USD"
        }
      ]
    },
    {
      "id": "message-id-2",
      "provider": "EBAY",
      "provider_message_id": "6270000000020",
      "sender_type": "AGENT",
      "sender_identifier": "aeliya-ship110",
      "recipient_identifier": "ricus-i8csgkrp",
      "body": "You sent a counteroffer $63.88",
      "read_status": true,
      "is_inbound": false,
      "sent_at": "2026-06-12T05:47:30.000Z",
      "attachments": [],
      "offers": [
        {
          "id": "offer-id-2",
          "message_id": "message-id-2",
          "conversation_id": "conversation-id",
          "offer_type": "SELLER_COUNTEROFFER",
          "direction": "OUTGOING",
          "status": "PENDING",
          "amount": "63.88",
          "offer_amount": "63.88",
          "currency": "USD"
        }
      ]
    }
  ],
  "offers": [
    {
      "id": "offer-id-1",
      "message_id": "message-id-1",
      "conversation_id": "conversation-id",
      "offer_type": "BUYER_OFFER",
      "direction": "INCOMING",
      "status": "PENDING",
      "amount": "45.00",
      "offer_amount": "45.00",
      "currency": "USD"
    },
    {
      "id": "offer-id-2",
      "message_id": "message-id-2",
      "conversation_id": "conversation-id",
      "offer_type": "SELLER_COUNTEROFFER",
      "direction": "OUTGOING",
      "status": "PENDING",
      "amount": "63.88",
      "offer_amount": "63.88",
      "currency": "USD"
    }
  ]
}
```

### Frontend Rule

The frontend should show an offer card only if the backend response contains either:

```text
message.offers[]
```

or a top-level offer with:

```text
offer.message_id == message.id
```

---

## 10. Local Data Models Involved

### `Conversation`

Main fields used by eBay sync:

```text
provider
provider_conversation_id
provider_account_id
subject
buyer_identifier
provider_conversation_status
provider_conversation_type
reference_id
reference_type
unread_count
last_message_at
external_created_at
raw_payload
```

### `Message`

Main fields used by eBay sync:

```text
conversation_id
provider
provider_message_id
sender_type
sender_identifier
recipient_identifier
body
read_status
is_inbound
sent_at
raw_payload
offer_data
```

### `MessageAttachment`

Main fields used by attachment sync:

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
download_url
raw_payload
```

### `Offer`

Main fields used by offer card sync:

```text
provider
account_id
conversation_id
message_id
reference_id
provider_offer_id
listing_id
buyer_username
offer_amount
currency
status
direction
offer_type
quantity
message
raw_text
expires_at
created_at_provider
raw_payload
```

---

## 11. Offer Extraction Logic Summary

Only process offers when:

```text
conversation.provider_conversation_type != FROM_EBAY
```

Supported offer phrases:

```text
sent an offer
sent a counteroffer
accepted an offer
accepted your offer
```

Valid offer examples:

```text
ricus-i8csgkrp sent an offer $45.00
You sent a counteroffer $63.88
buyer accepted an offer $63.88
You sent an offer INR 9,444.76
```

Invalid examples that should not create offer rows:

```text
Here is the best offer for this unit. Looking forward to your purchase!
Hi dear. Tell me your best deal if I buy it now please.
Available?
Can you make good discount?
```

### Parsed Output Example

Input:

```text
You sent an offer INR 9,444.76
```

Output:

```json
{
  "offer_type": "SELLER_OFFER",
  "direction": "OUTGOING",
  "status": "PENDING",
  "amount": "9444.76",
  "currency": "INR",
  "raw_text": "You sent an offer INR 9,444.76"
}
```

---

## 12. Quick API-to-Database Mapping

| API / Source | Response Root | Main Data | Stored In |
|---|---|---|---|
| Message API conversation list | `conversations[]` | Conversation summary | `conversations` |
| Message API conversation detail | `messages[]` | Message bodies, sender, recipient, dates | `messages` |
| Message API message media | `messageMedia[]` | Attachments/images | `message_attachments` |
| Trading API GetMyMessages | `messages[]` | Seller message headers / subjects | `messages`, `offers` when valid non-FROM_EBAY offer event |
| Trading API GetBestOffers | `offers[]` | Buyer Best Offer data | `offers` |
| Sell Fulfillment Orders API | `orders[]` | Orders and line items | order tables / conversation order context |
| Browse API item lookup | item object | Title/image/seller/item URL | product context / conversation sidebar |
| Local conversation detail API | `conversation`, `messages`, `offers` | UI-ready conversation thread | frontend render |

---

## 13. Example End-to-End Flow

### eBay conversation detail returns

```json
{
  "conversationType": "FROM_MEMBERS",
  "messages": [
    {
      "messageId": "m1",
      "messageBody": "ricus-i8csgkrp sent an offer $45.00",
      "senderUsername": "ricus-i8csgkrp",
      "recipientUsername": "aeliya-ship110",
      "readStatus": true,
      "createdDate": "2026-06-12T05:47:00.000Z"
    }
  ]
}
```

### Backend stores message

```json
{
  "provider": "EBAY",
  "provider_message_id": "m1",
  "sender_identifier": "ricus-i8csgkrp",
  "recipient_identifier": "aeliya-ship110",
  "sender_type": "CUSTOMER",
  "is_inbound": true,
  "body": "ricus-i8csgkrp sent an offer $45.00",
  "sent_at": "2026-06-12T05:47:00.000Z"
}
```

### Backend extracts offer

```json
{
  "provider": "EBAY",
  "conversation_id": "conversation-id",
  "message_id": "message-id",
  "offer_type": "BUYER_OFFER",
  "direction": "INCOMING",
  "status": "PENDING",
  "offer_amount": "45.00",
  "currency": "USD",
  "raw_text": "ricus-i8csgkrp sent an offer $45.00"
}
```

### Frontend receives and renders

```text
Message bubble:
  ricus-i8csgkrp sent an offer $45.00

Offer card:
  Buyer sent an offer
  USD 45.00
```

---

## 14. Final Implementation Notes

1. Store all messages normally first.
2. Skip offer extraction for `FROM_EBAY`.
3. Detect offers only from non-`FROM_EBAY` eBay-style offer event messages.
4. Extract only amount/currency plus offer type/direction/status.
5. Link every offer to `conversation_id` and `message_id`.
6. Return offers with messages in the conversation detail API.
7. Frontend should never parse message body or subject for offers.
8. Repeated sync must not create duplicate offers.

