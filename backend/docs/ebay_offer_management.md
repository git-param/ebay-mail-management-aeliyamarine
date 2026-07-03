# eBay Seller Offer Management

## Purpose

This feature lets an agent send an eBay seller-initiated offer from a help-desk conversation and displays offers sent by this application in the conversation thread.

eBay does not provide an API for retrieving the complete history of seller-initiated offers. For that reason, the application saves every offer immediately after eBay accepts the send request.

## How seller-initiated offers work in eBay

### 1. Eligibility is determined by eBay

An interested buyer may become eligible after watching an item, adding it to a cart, or otherwise showing interest. The seller cannot choose an arbitrary buyer for this API.

The Negotiation API exposes eligible listings through:

```http
GET /sell/negotiation/v1/find_eligible_items
X-EBAY-C-MARKETPLACE-ID: EBAY_US
```

The response contains `eligibleItems[].listingId`. Eligibility is listing-based and can change over time.

Important: `find_eligible_items` does not identify a help-desk conversation or expose the eligible buyers. The application must correlate the returned `listingId` with the eBay Item ID stored on a conversation.

### 2. Sending an offer

The application sends an offer through:

```http
POST /sell/negotiation/v1/send_offer_to_interested_buyers
X-EBAY-C-MARKETPLACE-ID: EBAY_US
Authorization: Bearer <seller access token>
```

Example request:

```json
{
  "allowCounterOffer": false,
  "message": "Here is the best offer for this item.",
  "offeredItems": [
    {
      "listingId": "123456789012",
      "quantity": 1,
      "price": {
        "value": "44.39",
        "currency": "USD"
      }
    }
  ]
}
```

This endpoint sends the offer to all buyers currently considered eligible by eBay for that listing. It is not a direct “send to this conversation's buyer” operation.

The response contains one `Offer` object for each buyer eBay contacted. Buyer names can be masked. Important response fields include:

- `offerId`
- `buyer.maskedUsername`
- `creationDate`
- `offerDuration`
- `offerStatus`
- `offeredItems[].listingId`
- `offeredItems[].price`

### 3. OAuth scope

The Negotiation API uses:

```text
https://api.ebay.com/oauth/api_scope/sell.inventory
```

eBay does not publish a separate `sell.negotiation` scope. The valid scope is already included in `EBAY_OAUTH_SCOPES`.

### 4. Historical and status limitations

There is no Negotiation API endpoint that lists all previously sent seller-initiated offers. `GetMyMessages` can contain notification text, but it is not a structured or reliable offer ledger.

Consequently:

- Only offers sent and successfully observed by this application are stored.
- The application calculates `EXPIRED` locally from `creationDate + offerDuration`.
- `ACCEPTED` or `DECLINED` cannot currently be refreshed from a historical Negotiation API call.

## How it works in this codebase

### Eligibility and conversation correlation

The conversation product context stores the eBay listing/Item ID in `reference_id`.

The frontend shows **Send offer** only when either condition is true:

```text
product_context.offer_available == true
product_context.cta_type == "SEND_OFFER"
```

The intended eligibility synchronization is:

```text
find_eligible_items.eligibleItems[].listingId
                    │
                    ▼
conversation_product_contexts.reference_id
```

If the IDs match, `offer_available` should be true. If they do not match, or the listing is no longer returned by eBay, it should be false.

The normal account synchronization calls `find_eligible_items` after message and order synchronization. It then replaces the cached eligibility flags for every listing context belonging to that seller account. Listings returned by eBay receive `offer_available = true`; listings absent from the complete response receive `false`.

Browse API `buyingOptions: BEST_OFFER` is deliberately not used for this flag. That value means a buyer can make a Best Offer and is different from seller-initiated offer eligibility.

### Request flow

```text
Conversation UI
    │ POST /api/v1/offers/send
    ▼
offers.py route
    │ checks conversation visibility
    ▼
EbayNegotiationService
    │ verifies listing belongs to the conversation
    │ obtains/refreshes the seller OAuth token
    ▼
EbayAuthClient.send_offer_to_buyer()
    │ POST send_offer_to_interested_buyers
    ▼
eBay Negotiation API
    │ returns Offer objects
    ▼
EbayNegotiationService
    │ stores each response immediately
    ▼
offers table
```

### Backend files

#### Negotiation client

`app/modules/integrations/ebay/client/ebay_auth_client.py`

`send_offer_to_buyer()` builds the eBay request, adds the marketplace header, and calls the shared JSON request helper. It returns an `EbayRawApiResponse` so the service can inspect both successful and failed eBay responses.

#### Negotiation service

`app/modules/integrations/ebay/services/ebay_negotiation_service.py`

The service:

1. Confirms that the submitted listing ID matches the conversation or its product context.
2. Finds the eBay seller account associated with the conversation.
3. Refreshes an expired access token when necessary.
4. Retries once after an eBay `401 Unauthorized` response.
5. Calls `send_offer_to_buyer()`.
6. Validates that eBay returned one or more structured offers.
7. Stores every returned offer in the same database transaction.
8. Converts locally expired `PENDING` offers to `EXPIRED` when offers are read.

An eBay failure is returned to the application as a `502 Bad Gateway` with eBay's useful error message when available.

#### Database model

`app/models/offer.py`

The `offers` table stores:

| Field | Meaning |
| --- | --- |
| `provider_offer_id` | eBay's unique `offerId` |
| `conversation_id` | Help-desk conversation owning the displayed event |
| `listing_id` | eBay legacy listing/Item ID |
| `buyer_username` | Masked buyer name returned by eBay |
| `offer_amount` | Offered unit price |
| `currency` | ISO currency code |
| `status` | `PENDING`, `ACCEPTED`, `DECLINED`, or `EXPIRED` |
| `message` | Seller message sent with the offer |
| `expires_at` | Calculated from eBay creation date and duration |
| `raw_payload` | Complete eBay response object for auditing/debugging |

`provider_offer_id` is unique, preventing the same eBay offer from being persisted twice.

The schema is created by `alembic/versions/20260702_0026_create_offers.py`.

#### API routes

`app/api/v1/routes/offers.py`

Send an offer:

```http
POST /api/v1/offers/send
```

```json
{
  "conversation_id": "conversation-uuid",
  "listing_id": "123456789012",
  "offer_amount": 44.39,
  "currency": "USD",
  "message": "Here is the best offer for this item.",
  "quantity": 1,
  "marketplace_id": "EBAY_US"
}
```

Retrieve offers persisted for a conversation:

```http
GET /api/v1/offers/conversation/{conversation_id}
```

Both endpoints apply the existing conversation visibility rules. An agent cannot use the offer endpoints to access a conversation outside their permitted queue.

### Frontend files

- `frontend/src/services/offerApi.js` calls the offer endpoints.
- `frontend/src/components/conversations/OfferPanel.jsx` loads, sends, and renders offers.
- `frontend/src/pages/dashboard.jsx` places offer events after the message thread.
- `frontend/src/App.css` styles the right-aligned message and offer cards.

Persisted offers remain visible even after the listing stops being eligible. The **Send offer** action disappears when `offer_available` is false, but previously sent offers remain part of the conversation history.

## Live eligibility synchronization

The account-level synchronization:

1. Calls `find_eligible_items` for every connected seller account and marketplace.
2. Follows all result pages.
3. Builds a set of eligible listing IDs for that seller account.
4. Sets `offer_available = true` for matching conversation product contexts.
5. Sets it to false for listings no longer returned.
6. Runs periodically and immediately before sending an offer.

The backend should still treat eBay as authoritative. Even when the cached flag is true, eBay can reject a send because eligibility changed between synchronization and submission. The UI should display that returned error and refresh eligibility.

## Buyer-originated Best Offers

Buyer offers are retrieved separately through the Trading API `GetBestOffers` call. They are not supplied as structured records by the REST Message API.

The asynchronous trigger is:

```http
POST /api/v1/offers/sync/account/{account_id}
```

This admin-only endpoint returns `202 Accepted` immediately. The eBay call, XML parsing, correlation, and database writes run in a background thread using a separate SQLAlchemy session. A production scheduler should call this endpoint periodically for every connected seller account. Conversation-detail requests never wait for eBay; they read only indexed local offer rows.

Buyer offers are deduplicated by eBay `BestOfferID` and correlated using all of:

1. The conversation's seller account.
2. The listing `ItemID`.
3. The conversation buyer identifier matching `Buyer.UserID`.

Exactly one conversation must match. Ambiguous or unmatched offers are retained with a null `conversation_id` and are not displayed in any conversation, preventing buyer data from appearing in the wrong thread.

Incoming cards display the buyer, amount, buyer message, status, expiry, and quantity. The implementation is in `ebay_best_offer_sync_service.py`; the Trading XML client is `get_best_offers_raw()` in `ebay_auth_client.py`.
