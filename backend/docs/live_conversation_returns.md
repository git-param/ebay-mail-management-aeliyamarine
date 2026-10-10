# Live conversation return details

The side panel's **Fetch return details** button calls
`GET /api/v1/conversations/{conversation_id}/live-returns` on demand. Optional
`order_record_id` selects one of the conversation's order candidates; `offset`
paginates results in batches of 10. The server validates the order's buyer and
account before any eBay request.

The connected production seller account is used for Post-Order
`GET /post-order/v2/return/search?order_id=...&role=SELLER`, followed by
`GET /post-order/v2/return/{returnId}?fieldgroups=FULL` for each result.
OAuth requests use `Authorization: IAF <access token>` and the order's listing
marketplace header. Sandbox requests are rejected because eBay does not support
these methods there. Expired account credentials use the existing token refresh
flow; credentials may be updated, but return payloads, order mappings, and
conversation read state are never written by this feature.

Responses have `Cache-Control: no-store`. The browser keeps results only in
component state, clears them on conversation/order changes or unmount, and
requests fresh results each time the button is pressed. Full-detail failures
retain the live search summary with a visible warning; search failures display
an error rather than incorrectly reporting no returns. The feature does not
approve returns or issue refunds.

References:
- https://developer.ebay.com/devzone/post-order/post-order_v2_return_search__get.html
- https://developer.ebay.com/Devzone/post-order/post-order_v2_return-returnid__get.html
- https://developer.ebay.com/devzone/post-order/concepts/MakingACall.html
