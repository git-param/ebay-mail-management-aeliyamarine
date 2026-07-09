# Backend Refactor Notes

## What Changed

- Simplified eBay offer direction inference to use confirmed data sources:
  - Commerce Message API payloads use `raw_payload["senderUsername"]`.
  - Stored messages use `Message.sender_identifier`.
  - eBay accounts use `EbayAccount.ebay_username`.
- Kept only confirmed compatibility fallbacks in the conversation offer resolver:
  - Commerce Message API uses camelCase fields such as `offerId`, `messageId`, `itemId`, and `listingId`.
  - Trading `GetMyMessages` is normalized by the backend client into snake_case fields such as `message_id` and `item_id`.
- Moved repeated "fill missing offer fields without overwriting good values" logic into `ebay_offer_validation.update_missing_offer_fields`.
- Removed the duplicate seller-offer service import/debug block from `ebay_sync_service.py`.
- Removed inline `sqlalchemy.or_` imports from seller offer matching and kept the import at module level.

## Where The Logic Lives

- eBay conversation/message sync:
  - `backend/app/modules/integrations/ebay/services/ebay_sync_service.py`
  - `backend/app/modules/integrations/ebay/services/ebay_message_service.py`
- Offer validation and safe normalization:
  - `backend/app/modules/integrations/ebay/services/ebay_offer_validation.py`
- On-demand offer cards from stored conversation messages:
  - `backend/app/modules/integrations/ebay/services/ebay_conversation_offer_resolver.py`
- Buyer-originated Best Offer API sync:
  - `backend/app/modules/integrations/ebay/services/ebay_best_offer_sync_service.py`
- Seller offer notifications from Trading `GetMyMessages`:
  - `backend/app/modules/integrations/ebay/services/ebay_seller_offer_sync_service.py`

## Compatibility Notes

- No API request/response shape was changed.
- No database model or migration was changed.
- No frontend code was touched.
- The `offers.direction` NOT NULL constraint remains enforced by the database; backend validation prevents invalid inserts before they reach the database.
