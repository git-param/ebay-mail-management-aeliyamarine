# Outbound eBay API Reference

This document lists external eBay APIs called by the ACES backend. The React frontend never calls eBay directly. Calls use the production host when `EBAY_ENVIRONMENT=PRODUCTION` and the sandbox host otherwise.

## Environment Hosts

| API family | Production | Sandbox |
|---|---|---|
| OAuth authorization | `https://auth.ebay.com` | `https://auth.sandbox.ebay.com` |
| OAuth/REST APIs | `https://api.ebay.com` | `https://api.sandbox.ebay.com` |
| Identity | `https://apiz.ebay.com` | `https://apiz.sandbox.ebay.com` |
| Media | `https://apim.ebay.com` | `https://apim.sandbox.ebay.com` |
| Trading API | `https://api.ebay.com/ws/api.dll` | `https://api.sandbox.ebay.com/ws/api.dll` |

Seller REST calls use `Authorization: Bearer <access_token>`. Trading calls use `X-EBAY-API-IAF-TOKEN`. OAuth token and Browse app-token calls use Basic authentication with the eBay client ID and secret.

## 1. OAuth Authorization

1. **API endpoint:** `GET /oauth2/authorize` on the authorization host.
2. **Response structure:** Browser redirect/consent flow. eBay returns to the configured callback with `code` and `state`, or `error` fields.
3. **What it does:** Lets a seller grant the configured scopes. ACES generates and stores `state`, then validates it on callback to prevent request forgery.

Important query parameters:

```text
client_id, redirect_uri (RuName), response_type=code, state, scope
```

Scopes requested by the code:

```text
commerce.message
commerce.identity.readonly
sell.inventory
sell.fulfillment
```

## 2. OAuth Token

1. **API endpoint:** `POST /identity/v1/oauth2/token`.
2. **Response structure:** `{access_token: string, refresh_token?: string, expires_in?: integer, refresh_token_expires_in?: integer, token_type?: string}`.
3. **What it does:** Exchanges an authorization code, refreshes a seller token, or obtains an application token for Browse API enrichment.

ACES uses form-encoded bodies with one of these grants:

```text
grant_type=authorization_code&code=...&redirect_uri=...
grant_type=refresh_token&refresh_token=...&scope=...
grant_type=client_credentials&scope=https://api.ebay.com/oauth/api_scope
```

Seller tokens and expiry timestamps are stored on `ebay_accounts`. Application tokens are cached in memory for listing enrichment.

## 3. Commerce Identity: Authenticated User

1. **API endpoint:** `GET /commerce/identity/v1/user/` on the Identity host.
2. **Response structure:** `{username, userId, businessAccount?: {doingBusinessAs?, ...}, ...}`; ACES normalizes this to `{username, user_id, seller_account_id, store_name}`.
3. **What it does:** Verifies that OAuth connected the expected seller username and captures the seller/store identity.

## 4. Commerce Message: List Conversations

1. **API endpoint:** `GET /commerce/message/v1/conversation?conversation_type={FROM_MEMBERS|FROM_EBAY}&limit={n}&offset={n}`.
2. **Response structure:** `{href?, next?, prev?, limit, offset, total, conversations: [{conversationId, conversationStatus, conversationTitle, conversationType, createdDate, referenceId?, referenceType?, unreadCount, latestMessage?}]}`.
3. **What it does:** Discovers buyer/member and eBay-system conversation IDs for synchronization. ACES pages both `FROM_MEMBERS` and `FROM_EBAY` and applies an incremental cursor when possible.

## 5. Commerce Message: Conversation Detail

1. **API endpoint:** `GET /commerce/message/v1/conversation/{conversation_id}?conversation_type={type}&limit={n}&offset={n}`.
2. **Response structure:** `{conversationTitle, conversationStatus, conversationType, referenceId?, referenceType?, total, messages: [{messageId, messageBody, senderUsername, recipientUsername, subject?, readStatus, createdDate, messageMedia?: [{mediaName, mediaUrl, mediaType}]}]}`.
3. **What it does:** Retrieves message bodies, participants, timestamps, read state, and attachments. ACES upserts the conversation/messages and derives customer, agent, provider, and inbound/outbound state.

## 6. Commerce Message: Send Message

1. **API endpoint:** `POST /commerce/message/v1/send_message`.
2. **Response structure:** eBay JSON acknowledgement containing provider message/conversation data; ACES preserves the raw payload and treats any successful 2xx response as sent.
3. **What it does:** Sends a reply in an existing eBay conversation.

Request structure:

```json
{
  "conversationId": "provider-conversation-id",
  "conversationType": "FROM_MEMBERS",
  "messageText": "Reply text",
  "emailCopyToSender": true,
  "messageMedia": [
    {"mediaName": "photo.jpg", "mediaType": "IMAGE", "mediaUrl": "https://..."}
  ]
}
```

## 7. Commerce Media: Create Image from File

1. **API endpoint:** `POST /commerce/media/v1_beta/image/create_image_from_file` or the configured `EBAY_MEDIA_BASE_URL` equivalent.
2. **Response structure:** JSON and/or `Location` header. ACES looks for `maxDimensionImageUrl`, `imageUrl`, or `mediaUrl`, and normalizes the result to include `mediaUrl` and `location` when available.
3. **What it does:** Uploads supported reply images to eBay before the send-message call. The request is multipart with an `image` file part.

## 8. Commerce Media: Get Image Resource

1. **API endpoint:** `GET {Location}` returned by Create Image from File.
2. **Response structure:** Image metadata containing `maxDimensionImageUrl`, `imageUrl`, or `mediaUrl`.
3. **What it does:** Resolves the final eBay-hosted media URL when the create response only returns a resource location.

## 9. Sell Fulfillment: List Orders

1. **API endpoint:** `GET /sell/fulfillment/v1/order?limit={n}&offset={n}&filter={optional_filter}`.
2. **Response structure:** `{href?, next?, prev?, limit, offset, total, orders: [{orderId, creationDate, lastModifiedDate, orderFulfillmentStatus, orderPaymentStatus, buyer, pricingSummary, lineItems, cancelStatus, paymentSummary?, ...}]}`.
3. **What it does:** Synchronizes orders and line items used by conversation order linking, sold posting, SKU/product context, returns/cancellations context, and reporting.

The sync generally requests up to 200 orders per page and stores the source payload alongside normalized order tables.

## 10. Sell Fulfillment: Get Order

1. **API endpoint:** `GET /sell/fulfillment/v1/order/{order_id}`.
2. **Response structure:** One Fulfillment order object with buyer, status, pricing, line-item, shipping, cancellation, and payment information.
3. **What it does:** Retrieves one order when a specific record needs direct refresh or inspection.

## 11. Buy Browse: Get Item by Legacy ID

1. **API endpoint:** `GET /buy/browse/v1/item/get_item_by_legacy_id?legacy_item_id={listing_id}`.
2. **Response structure:** `{itemId, legacyItemId?, title, image?: {imageUrl}, price?: {value, currency}, itemWebUrl, seller?: {username}, buyingOptions?: string[], ...}`.
3. **What it does:** Enriches listing-linked conversations when equivalent product data is not already available from local order/context records.

This call uses a client-credentials application token and sends `X-EBAY-C-MARKETPLACE-ID` from `EBAY_MARKETPLACE_ID`.

## 12. Trading API: GetBestOffers

1. **API endpoint:** `POST /ws/api.dll` with `X-EBAY-API-CALL-NAME: GetBestOffers`.
2. **Response structure:** XML `GetBestOffersResponse`; ACES normalizes it to `{ack, totalPages, error, offers: [{offerId, listingId, buyerUsername, buyerMessage, sellerMessage, expirationTime, amount, currency, quantity, status, offerType, createdTime}]}`.
3. **What it does:** Synchronizes buyer offers across listings and stores normalized offer records linked to accounts, listings, conversations, and messages.

The request uses compatibility level `1455`, site ID `0`, `BestOfferStatus=All`, and pagination up to 200 entries per page.

## 13. Trading API: GetMyMessages

1. **API endpoint:** `POST /ws/api.dll` with `X-EBAY-API-CALL-NAME: GetMyMessages`.
2. **Response structure:** XML `GetMyMessagesResponse`; ACES normalizes it to `{ack, total_pages, error, messages: [{message_id, subject, body, sender, recipient, message_type, sent_date, receive_date, item_id, message_status, read, flagged}]}`.
3. **What it does:** Retrieves eBay My Messages headers or full message details, including provider notifications that can be resolved into seller-offer events.

The code supports `DetailLevel=ReturnHeaders`, `ReturnMessages`, page selection, and targeted message IDs.

## 14. Trading API: AddMemberMessageAAQToPartner

1. **API endpoint:** `POST /ws/api.dll` with `X-EBAY-API-CALL-NAME: AddMemberMessageAAQToPartner`.
2. **Response structure:** XML acknowledgement/error payload, returned internally as `{status_code, ok, payload, request_url, sanitized request_headers}`.
3. **What it does:** Sends a seller message to a member for listing/question flows that require the legacy Trading message operation.

The XML request contains `ItemID`, `MemberMessage` (`Body`, `RecipientID`, `Subject`, `QuestionType`, optional `MessageMedia`), and a correlation `MessageID`.

## 15. Trading API: AddMemberMessageRTQ

1. **API endpoint:** `POST /ws/api.dll` with `X-EBAY-API-CALL-NAME: AddMemberMessageRTQ`.
2. **Response structure:** XML acknowledgement/error payload, returned internally as `{status_code, ok, payload, request_url, sanitized request_headers}`.
3. **What it does:** Replies to a member question using `ParentMessageID` when the Commerce Message send path is not the appropriate provider operation.

## 16. Sell Negotiation: Get Offer

1. **API endpoint:** `GET /sell/negotiation/v1/offer/{offer_id}`.
2. **Response structure:** An eBay offer object containing offer ID, status, creation/expiry data, buyer, listing, quantity, price, and message fields as supplied by the Negotiation API.
3. **What it does:** Resolves additional details for a known provider offer when synchronized Trading/My Messages data is incomplete.

## Call Flows

### OAuth Connection

```text
ACES connect endpoint
  -> OAuth authorization
  -> OAuth callback
  -> OAuth token exchange
  -> Commerce Identity
  -> store account identity and encrypted/secured token fields
```

### Account Synchronization

```text
refresh seller token when needed
  -> list conversations (FROM_MEMBERS and FROM_EBAY)
  -> get each selected conversation
  -> enrich missing listings through Browse
  -> list Fulfillment orders
  -> GetBestOffers pages
  -> GetMyMessages headers/details where used
  -> normalize and commit PostgreSQL records
```

### Reply with Attachments

```text
validate reply
  -> create eBay media image
  -> resolve media resource URL when necessary
  -> Commerce send_message or Trading member-message call
  -> persist outbound message and attachment delivery state
```

## Error and Retry Behavior

- Provider HTTP failures are normalized by the backend and normally surface to clients as `502 Bad Gateway` or a failed sync record.
- Access tokens are refreshed before calls when expired and may be refreshed/retried after authentication failure.
- Browse enrichment uses `EBAY_BROWSE_MAX_RETRIES` and `EBAY_BROWSE_RETRY_BASE_SECONDS`.
- Synchronization records failures in sync logs and continues per-record where the service can safely do so.
- Authorization, Basic credentials, bearer tokens, and `X-EBAY-API-IAF-TOKEN` values must never be logged or returned unredacted.

## Implementation Locations

- API client: `backend/app/modules/integrations/ebay/client/ebay_auth_client.py`
- OAuth services: `backend/app/modules/integrations/ebay/oauth/`
- Sync orchestrator: `backend/app/modules/integrations/ebay/services/ebay_sync_service.py`
- Order provider/sync: `backend/app/modules/integrations/ebay/orders/`
- Offer sync: `backend/app/modules/integrations/ebay/services/ebay_best_offer_sync_service.py`
- Listing enrichment: `backend/app/services/conversation_product_context_service.py`
- Reply orchestration: `backend/app/services/ebay_reply_service.py`
- Attachment upload: `backend/app/services/reply_attachment_service.py`
