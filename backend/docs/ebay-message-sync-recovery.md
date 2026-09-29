# Missing eBay conversations and offers from another buyer

## Findings

The code contains several independent paths that can produce the reported symptoms. These findings come from code inspection and regression tests; no live eBay account or production database was queried.

1. **Failed imports became permanently older than the sync cutoff.** `EbaySyncService._finalize_sync` advanced `last_sync_at` even after conversation failures or a capped import. `_iter_conversation_summaries` then skipped older summaries without checking whether they had actually been stored. It also stopped scanning after an entirely old page, so missing conversations on later pages could never be discovered. The creation date fallback was unsafe for conversations whose latest-message date was absent.
2. **Only the first 50 messages were imported.** The detail endpoint was called once with `offset=0`. Long conversations lost the remaining messages. eBay documents paginated responses with `total`, `next`, `limit`, and `offset`: [getConversation](https://www.developer.ebay.com/develop/api/commerce/message_api/conversation/getConversation).
3. **An offer failure could roll back message imports.** `EbayConversationOfferResolver` called `Session.rollback()` on offer insert/parse failures. That rolls back the outer transaction, including pending conversation/message inserts; the conversation savepoint did not protect against an explicit full rollback. Product enrichment also ran inside the message import savepoint, so its failure discarded the messages.
4. **An offer could be linked to the wrong buyer.** `EbayBestOfferSyncService._match_conversation` tried a buyer match, then fell back to the only conversation for the listing. For an offer by buyer 1 and a sole chat with buyer 2, that fallback returned buyer 2's conversation.
5. **Buyer and notification detection added confusion.** Buyer detection used a case-sensitive comparison with the seller username and could select `ebay` as the buyer. Offer parsing also included the conversation title for every message, allowing an older offer title to classify ordinary follow-up chat as another offer.

The conversation table has a unique key on `(provider, provider_conversation_id)`; messages have one on `(provider, provider_message_id)`. There is no conversation uniqueness constraint on item/listing ID. Two buyers asking about the same item can therefore have separate conversations. Existing provider-ID keys remain unchanged. Actual constraint failures should be identified through `SyncLog.sync_metadata.failed_conversations`, which includes provider conversation IDs and error text, before changing the schema.

## Implemented behavior

- Scan every conversation-list page. Skip an older conversation only when this account has an import marked complete by the updated implementation and its stored activity is at least as recent as the summary. A five-minute overlap rechecks recent activity. Missing latest-message timestamps trigger a detail fetch.
- Fetch every detail page before saving; reject incomplete pages and messages missing IDs so the conversation stays retryable.
- Advance the account cutoff to the sync start time only after an uncapped run without failed conversation imports.
- Isolate product enrichment and offer resolution with savepoints. Imported messages survive enrichment failures, and conversations with failed enrichment remain eligible for another attempt.
- Require account, listing, and buyer identity when linking best offers. Offers without a matching buyer remain stored without a conversation link. Replay detaches existing links to a different buyer/listing and clears their stale message links. Terminal offers also have their links corrected when re-observed.
- Compare usernames without case differences, exclude seller/eBay identities from buyer detection, and detect offer events from each message's subject/body.

## Recovery after deployment

Run the ordinary account message sync without a `max_conversations` cap. Existing conversations lack the new `raw_payload.message_sync_version` marker, so the first run replays their full history and repairs offer associations. Missing conversations returned by eBay are imported even if their timestamps precede the previous cutoff. No manual cutoff reset or database migration is required.

The first recovery run makes more detail requests and can take longer than a normal incremental sync. Later runs reuse the completion marker. Failed imports stay eligible for later syncs. Inspect `failed_conversations` in the sync log and enrichment exceptions in backend logs for unresolved provider or payload failures.

This recovery cannot import conversations eBay does not return, and does not split or delete messages inside a conversation supplied as mixed by eBay itself. If a specific conversation is still missing after recovery, compare its eBay conversation ID and raw provider response with the sync log. The changes do not establish that every reported production example had the same cause.

## Verification

`tests/test_ebay_sync_recovery.py` covers pagination beyond 50 messages, later-page failures, malformed messages, old missing/legacy conversations, watermark behavior, buyer isolation, stale offer link repair, notification detection, and preserving message imports after enrichment/offer failures. SQLite tests exercise ORM queries, unique constraints, and savepoints; they do not replace a production PostgreSQL/provider check.
