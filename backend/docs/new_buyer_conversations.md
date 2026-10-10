# New buyer conversations

In the Inbox, select **New buyer**, choose an active connected eBay account,
and enter the buyer's exact eBay username. Select **Open conversation** to
compose the first message using the existing templates, message types, and
attachment controls. The buyer does not need an ACES order or conversation.

The recipient is checked by eBay when the message is sent. Opening the composer
does not verify that the username exists or create a database conversation.
Provider rejection messages are shown in the composer, preserving the draft.

## API and implementation

- `POST /api/v1/conversations/start/validate` validates message policy without a thread ID.
- `POST /api/v1/conversations/start` accepts multipart form fields `account_id`,
  `buyer_username`, `body`, `message_type_id`, `send_copy_to_email`, and optional
  `attachments`. Both endpoints require authentication.
- `NewBuyerConversationService` validates the selected sending account and
  recipient. If an open member conversation already exists for that account and
  buyer, it sends through that conversation. Otherwise it creates a transient
  thread and delegates delivery to `EbayReplyService`.
- The first eBay message uses `otherPartyUsername` rather than `conversationId`.
  The selected account's token supplies the sender identity. The existing reply
  flow handles attachments, classification, audit logging, and persistence.
- Failed delivery rolls back the transient conversation and pending message.
- A returned eBay `conversationId` replaces the temporary identity immediately.
  If eBay omits it, the accepted message is saved locally and subsequent sends
  wait for the normal message sync. Sync attaches the provider identity only
  when the outbound message matches by ID or by body, sender, recipient, and
  timestamp. This avoids starting another conversation accidentally.

No database migration is required. Live delivery still depends on the connected
account's eBay Message API access and eBay's recipient restrictions.

## Starting from Sold Posting

Click an order ID to open the latest open member conversation for that buyer
and the order's owning account. If none exists, the Inbox opens the composer
with the buyer, account, and order already selected. The recipient and sender
cannot be changed in this order flow.

`POST /api/v1/sold-posting/orders/{order_id}/conversation?account_id=...` resolves
the order within its seller account. First-message requests include `order_id`;
the backend reads the buyer from the stored order again and associates the new
conversation with the order's listing when available. Missing buyer usernames
produce a clear error instead of opening an empty recipient form.

New messages and subsequent replies include the Message API `reference` container
when a listing ID is available from the conversation, order mapping, or linked
order: `referenceType: LISTING` and `referenceId: <item ID>`. This supplies eBay
with the listing context for its product card. Username-only messages omit the
reference. Previously delivered messages are not modified; eBay controls how
the context appears in its UI.

Opening an existing thread from Sold Posting persists the exact selected order
and its order context mapping before navigation. First sends attach the order
for both new and reused conversations. Missing records in the conversation
`orders` table are populated from the stored Sold Posting payload. Normal message
sync preserves this explicit mapping. eBay's Message API supports only listing
references; it has no order-ID request field, so an eBay order banner cannot be
guaranteed through this API.
