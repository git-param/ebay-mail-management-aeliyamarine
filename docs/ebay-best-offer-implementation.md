# eBay Best Offer implementation report ? 2026-09-26

## Scope expanded: buyer, seller, active and historical offers

### Efficient current-offer monitoring (2026-09-28)

Routine sync reads paginated account-wide Active offers without depending on eBay messages. Unchanged active listings do not incur redundant ItemID/All calls. Previously current offers that disappear, recent verified buyer-waiting states, and unresolved financial actions receive due listing-specific reconciliation. Confirmed accepted/closed offers move out of Current Offers into Saved History. An empty provider response does not invent an accepted or expired status.

The optional history refresh checks at most 25 due listings with verified terminal offers from the last 30 days per account. It never sweeps old conversations, legacy unknown records, or orphan listing states. The limit counts listings; pagination and authentication retry can add API attempts. Current-offer reconciliation is separate from this optional budget.

Config polls a running job every 10 seconds (30 seconds in a hidden tab), stops on completion, and pauses configuration polling during a job. Enabled idle scheduling checks configuration once per minute. These local requests do not consume eBay API quota. Stop current sync records a cancellation request; the worker stops before its next provider request and preserves stored records.

Offer updates appear after a successful scheduled/manual sync; automatic synchronization must be enabled for continued monitoring. No webhook or email notification is needed for the Trading offer polling path. Earlier broad-history behavior described below has been superseded.

### Current cache and latest buyer/item entries (2026-09-28)

Current Offers now defaults to the latest complete account-wide Active scan. A successful scan atomically replaces the account's visible offer IDs, including replacing the set with zero IDs when eBay returns no offers. A dedicated SUCCESS snapshot record in the existing SyncLog table stores this membership; failed, stopped, malformed, or unknown-role scans never publish a partial set. Offer rows remain available to conversation history and action ledgers. Saved history is an explicit separate view and never exposes action controls.

Both views select one newest offer per account, normalized buyer username, and item ID **before** status/search filters, counts, sorting, or pagination. Provider creation/received timestamps establish chronology; numeric provider offer IDs break timestamp ties, including legacy bulk import timestamps. Missing buyer/item identities are kept separate. Actions also verify that the selected offer is the latest member of the current account snapshot.

Routine synchronization no longer scans archived conversation/listing candidates. Optional saved-history refresh is limited to 25 recent verified terminal listings, while current/unresolved verified offers continue using due listing checks. Trading error 20140 (no Best Offers found) is an authoritative empty result, not a failed job; other errors retain normal failure behavior. Historical listing notes are collapsed in Config. No migration is required. Existing accounts need one successful Sync now to populate their current cache.

### Earlier two-pass synchronization and lifecycle status

Synchronization combines paginated account-wide `Active` discovery with due listing-specific `ItemID + All` reconciliation. The candidate set includes discovered listings, unresolved offers, verified buyer-waiting states, recent `FROM_MEMBERS` conversations, and recent existing listing sync states. Normal runs use a 30-day conversation horizon; **Include older offer history** expands it to 365 days and includes known legacy Trading identities. The account-wide request remains `Active` in both modes.

`provider_status` remains the exact eBay value. The query API additionally returns a human-readable `display_status` and `status_group`: OPEN, AGREED, COMPLETED, CLOSED, or UNKNOWN. SellerAccept and buyer confirmation/payment states belong to AGREED, not paid COMPLETED. AdminEnded belongs to CLOSED. Existing broad internal status strings remain compatible with conversation history; no database migration or enum expansion is required. Unknown future states stay visible and cannot resolve ambiguous actions.

Successful listing checks persist their count and timestamps in the existing listing state table. Open offers and buyer confirmation poll after five minutes; buyer payment after fifteen minutes; verified terminal offers after seven days; empty listings after twelve hours. Unresolved actions retain five-minute reconciliation. Provider failures retain exponential backoff and unavailable listings retain seven-day backoff. New conversation activity can wake an otherwise deferred listing without bypassing error backoff. Unknown roles remain excluded unless a previous verified offer can supply its own role. Both grouped and flat XML shapes preserve available role and listing metadata.

Current Offers provides lifecycle filters, grouped exact-status options, deliberate lifecycle summary counts, and waiting-state labels in place of stale countdowns. Cards and action dialogs display listing prices only when their currency matches the offer. Config reports active discovery, reconciled listings, new offers, status changes, other updates, unchanged observations, and API attempts separately. Worker, locking, permissions, and single-dispatch action behavior remain in place.

Official API references: [GetBestOffers](https://developer.ebay.com/devzone/xml/docs/reference/ebay/GetBestOffers.html) and [BestOfferStatusCodeType](https://developer.ebay.com/devzone/xml/docs/reference/ebay/types/BestOfferStatusCodeType.html).

### Earlier latest-change synchronization

Normal manual and automatic synchronization now checks active Trading offers and unresolved status changes, compares provider snapshots, and reports new, updated and unchanged counts. It skips routine scans of legacy history. Manual sync offers an optional **Also refresh older stored history** checkbox; saved history remains visible in either mode.

GetBestOffers does not expose a modified-since filter (https://developer.ebay.com/devzone/XML/docs/Reference/eBay/GetBestOffers.html). This is selective polling with local change detection, not a server-side delta feed. GetSellerEvents listing modification windows do not cover all buyer/seller offer changes and are not used as an equivalent.

A read-only diagnostic for Main listing 334577127872 returned eBay error 21549: the listing is invalid, not activated, or no longer in eBay's database. This old-history error previously appeared only as RuntimeError. Unavailable listings now produce a readable note, preserve stored offers and receive a seven-day recheck backoff. Other failures retain readable error details. A new regression also caught and fixed initialization of retry counts after a rolled-back listing request.

Offer cards explain buying/selling roles and unverified history, distinguish ACES processing dates from confirmed provider checks, label cached prices, and show accepted/expired records as closed. All Offers initially sorts newest records first. Zero results describe the Trading API scope rather than claiming that the account has no offers anywhere on eBay. The separate notification-feed coverage limitation below still applies.

Validation: 57 dedicated tests passed, including PostgreSQL regressions for unchanged versions, skipping legacy history by default and preserving unavailable history. Frontend build and targeted ESLint passed; existing bundle-size and Pydantic deprecation warnings remain. No migration is required.

The user subsequently authorized displaying both account roles and expired history. This supersedes the seller-only view described in the original report below.

- All Offers now defaults to all stored non-synthetic offers, including buyer records and legacy/message history. Role and status filters are local. Historical/unverified records are labelled and cannot receive live seller actions.
- Account-wide Trading discovery retains both explicit Buyer and Seller roles. Historical reconciliation supports both roles and refreshes known legacy Trading identities by listing. Unknown roles are never assigned by guesswork.
- The current configured database exposes 870 non-synthetic records through this view, including stored expired statuses. Matching cached account/item product metadata supplies available titles and images.
- The screenshot's seller-initiated discounts are a separate source. A live Main account-wide GetBestOffers response reports zero entries; its token identity matches aeliya110. A listing-specific request for 315776110438 returned provider error 21549. GetMyeBayBuying did not yield a usable response in the diagnostic request (provider XML failure). No historical buyer discounts were fabricated or imported from screenshots.
- eBay documents OFFER_ACTIVITY notifications for buyer and seller offers, including SELLER_OFFER sent to buyers: https://developer.ebay.com/develop/api/buy/notification_events . That feed is not connected in this implementation. Complete capture of those discounts requires webhook/subscription setup and relevant authorization; previously missed expired offers may not be retrievable through the existing Trading polling API. The UI states this coverage limit.

Validation for this expansion: 55 dedicated Best Offer tests passed; frontend production build and lint of the three modified components passed. No migration is required for this expansion. Seller action provenance and permission checks remain unchanged.


The existing Offer model and importer now support account-wide seller Best Offers, local Current Offers queries, persistent scheduling, spawned synchronization jobs, and guarded Accept/Decline/Counter actions. Existing manual Offer Entries remain mounted under their own tab. No PMS files were changed and no Best Offer action awards PMS credit.

## Screenshot: why a successful sync can show zero

The supplied My eBay screenshot shows four OFFER EXPIRED rows and buyer-facing controls, including Make Best offer and View seller's other items. These appear to be buyer-side offers, rather than active Best Offers received by your configured accounts as sellers. Normal discovery requests BestOfferStatus=Active without an ItemID. Expired offers are outside that discovery; buyer and unknown roles are excluded from Current Offers.

The saved six-account jobs completed successfully with zero imported seller records. Those older jobs did not record returned/filtered counts, so their results alone do not prove whether the provider response was empty. New results record discovery pages, records returned, verified seller records, buyer records skipped, and unknown-role records skipped. Config displays these counts and the scope explanation. No buyer/unknown role is guessed to be Seller.

## Database and migration

Migration `backend/alembic/versions/20260926_0061_extend_ebay_best_offers.py` is applied to the configured database; Alembic reports `20260926_0061 (head)`.

Offer additions: record_source, exact provider_status/provider_role, provider_snapshot, listing_snapshot, received_at/received_at_source, first_seen_at, last_seen_at, last_synced_at, last_seen_sync_id, reconciliation_required and version. Identity remains provider + account + BestOfferID. Existing message and derived records remain available to conversation history but cannot receive live actions. Historical unknown-role records remain excluded until verified. Conversation/message deletion detaches durable Trading history.

Supporting tables: ebay_best_offer_actions is the durable intent/result ledger; ebay_api_call_attempts records account/operation/job/action attempt attribution linked to the existing shared usage counter. Existing listing sync state gains reconciliation timing/backoff fields. Partial unique indexes protect pending/running account and batch jobs and unresolved offer actions. Migration table definitions are frozen. Downgrade refuses to discard accumulated action/attempt history; the entitlement and SET NULL protection deliberately survive an empty downgrade.

Only api.ebay_bestseller_daily_limit was changed to 2,500,000. Verification found Commerce still 5,000 and Fulfillment still 1,000.

## Synchronization and worker behavior

The existing ebay_best_offer_sync_service.py performs all account-wide Active pages and only admits explicit Seller roles. Its existing upsert path retains conversation linkage and derived history. Row savepoints prevent one malformed row from losing successful rows. A complete discovery scan flags known unresolved seller offers missing from Active; listing-specific All reconciliation processes all pages. Exact terminal/payment states are retained, absence does not invent a decline or expiration, and ambiguous actions still showing Active remain scheduled for reconciliation. Per-listing backoff covers failures without imposing the old 1,000/day cap or a fixed historical listing-count cap.

Configuration uses existing app_config_settings. A scheduler checks the persisted interval and eligible selected accounts. Reservation uses PostgreSQL protection and PENDING/RUNNING SyncLog rows. Only newly_reserved results spawn a non-daemon process; token-checked compare-and-set claims and account advisory locks prevent duplicate execution across processes and existing message importers. Per-account failures are isolated. Stop is checked between requests/pages/accounts; an in-flight provider request may finish. Shutdown supervises owned children and records interrupted jobs. Restart recovery never replays an interrupted response action. Thread cancellation waits for an outstanding reservation/dispatch before worker shutdown.

## Actions and permissions

Accept, Decline and Counter use RespondToBestOffer. The server verifies permission, authoritative Trading provenance, Seller role, active connected account, compatible environment, state, expiration, expected version and available quantity/currency before dispatch. Counter amount is the TOTAL for the chosen quantity; quantity and message length (250 characters) are validated. Single-item counters cannot exceed a known same-currency listing price.

An action intent is committed before accounting and DISPATCHING state. Shared quota and attribution reserve atomically in an independent short transaction; failed transport attempts and additional GET authentication attempts count conservatively. A response needs operation CallStatus=Success plus acceptable Ack, not HTTP 200 alone. Timeouts, malformed replies and uncertain persistence produce RECONCILIATION_REQUIRED and block conflicting actions. A reused idempotency key returns its prior result; no ambiguous Respond request is automatically retried. Confirmed local success does not invent payment or provider status. Subsequent synchronization reconciles state.

Admin and Ops Manager can configure, start/stop and manually synchronize. Agent can view Current Offers and respond only with offer.respond; Config is hidden and its endpoints return 403. New permission grants cover existing Admin/Ops/Agent role names. Configuration changes, start/stop, manual synchronization and response results are audited. OAuth authorization now includes the standard Trading scope, with refresh fallback preserving existing grants.

## UI and compatibility

Offer Management has Offer Entries / See Current Offers / Config segmented navigation in the existing page/sidebar location. Manual state stays mounted when switching sections. Current Offers uses responsive cards, available cached account/item metadata, exact provider status, offer/listing amounts and currency, buyer/message/IDs, quantity, first-seen versus received provenance, expiration and a local countdown. Server-side account/status/search/buyer/item filters, sorting and pagination query PostgreSQL only. Actions use confirmation dialogs and disable duplicate submission. Config persists hours/minutes/account selection, supports manual sync while stopped, polls jobs, shows per-account results and discovery diagnostics. eBay Accounts retains its cards and operations with shared Trading quota and per-account GetBestOffers/RespondToBestOffer attribution.

## Commands actually executed

| Command/check | Result | Important output |
| --- | --- | --- |
| `.venv/Scripts/python.exe -B -m alembic upgrade head` | PASS after fix | Initial attempt failed on a colon interpreted as a SQL bind; fixed and upgrade applied transactionally. Final rerun succeeds. |
| `.venv/Scripts/python.exe -B -m alembic current` | PASS | 20260926_0061 (head). |
| Application import and OpenAPI generation | PASS | All six new Best Offer paths registered. Existing duplicate operation-ID warnings occur in unrelated routers. |
| Initial `npm run build` / `npm run lint` | FAIL (launcher) | PowerShell blocked npm.ps1; subsequent commands use npm.cmd. |
| `npm.cmd run build` | PASS after JSX fix | 118 modules transformed; final production build succeeds. Existing large bundle warning remains. |
| `npm.cmd run lint` | FAIL | Repository-wide lint errors include existing React hook/purity errors. |
| Node ESLint check against HEAD for every failing file | PASS for regression check | 34 current errors, 34 baseline errors, zero additional errors; 12 current warnings. |
| `npm.cmd exec eslint -- src/pages/offer_management/BestOfferCard.jsx src/pages/offer_management/BestOfferActionDialog.jsx src/pages/offer_management/BestOfferConfig.jsx src/pages/offer_management/CurrentOffers.jsx src/pages/offer_management/bestOfferFormat.js src/services/ebayBestOfferApi.js` | PASS | New frontend files lint clean. |
| Initial backend pytest command | FAIL (dependency) | pytest absent. Installed pytest in existing virtual environment; API TestClient also needed httpx2, installed subsequently. Added requirements-dev.txt. |
| Existing backend suite: `.venv/Scripts/python.exe -B -m pytest -p no:cacheprovider tests -q` | FAIL | 41 passed, one unchanged translation test failed, three subtests passed. |
| Dedicated Best Offer tests with ACES_RUN_POSTGRES_TESTS=1 | PASS after fixture/dependency fixes | Latest dedicated run: 51 passed; two further tests were then added and covered by final full-suite run. |
| Final `$env:ACES_RUN_POSTGRES_TESTS='1'; .venv/Scripts/python.exe -B -m pytest -p no:cacheprovider tests -q --tb=short` | FAIL overall; Best Offer tests PASS | 94 passed, one failed, three subtests passed. All 53 Best Offer tests pass, including startup/shutdown, real spawned worker exit, API RBAC, stale-dispatch recovery, pagination, seller filtering, savepoints, durable idempotency, reconciliation and concurrent quota reservation. Only failure: test_translate_to_english_returns_english_text_without_provider in untouched translation code. |
| AST parsing of changed Python files | PASS | 30 changed/new Python files parsed at check time. |
| `git diff --check` | PASS | No whitespace errors. |
| Database configuration/test-schema verification | PASS | Trading 2.5M; Commerce 5K; Fulfillment 1K; auto stopped, interval five minutes, six accounts configured; no disposable test schemas remain. |

PostgreSQL tests clone empty public table definitions into validated disposable schemas and remove them afterward. Application rows are not mutated by those tests. Provider calls in tests are mocked, including financial actions. Real financial Accept/Decline/Counter operations were not sent as a test.

## Remaining limitations and manual steps

Repository-wide checks are not fully green: the unchanged translation test and baseline frontend lint errors remain. Live successful seller actions have not been validated against an actual actionable offer. Product fields stay empty where neither provider output nor matching cached metadata supplies them. Previously unverified historical roles are not guessed. Interrupted actions cannot be retried until authoritative reconciliation resolves their state.

The database migration is already applied. Reload/restart the running backend if its development reloader has not loaded the latest changes, then rerun Sync Now to obtain the new diagnostic counts. Automatic synchronization is currently stopped; Start Auto Sync in Config is required if automatic cycles are desired. Existing authorization grants may require reconnecting only if eBay rejects the newly required Trading scope; the saved zero-result jobs contain no authentication failure.

Official behavior reference: [GetBestOffers](https://developer.ebay.com/devzone/xml/docs/reference/ebay/GetBestOffers.html), [RespondToBestOffer](https://developer.ebay.com/devzone/xml/docs/reference/ebay/RespondToBestOffer.html).

## Created and modified files

- `backend/alembic/versions/20260926_0061_extend_ebay_best_offers.py`
- `backend/app/api/v1/router.py`
- `backend/app/api/v1/routes/offers.py`
- `backend/app/db/base.py`
- `backend/app/main.py`
- `backend/app/models/__init__.py`
- `backend/app/models/conversation.py`
- `backend/app/models/ebay_api_call_attempt.py`
- `backend/app/models/ebay_best_offer_action.py`
- `backend/app/models/ebay_best_offer_listing_sync_state.py`
- `backend/app/models/offer.py`
- `backend/app/modules/config_management/defaults.py`
- `backend/app/modules/config_management/service.py`
- `backend/app/modules/integrations/ebay/client/ebay_auth_client.py`
- `backend/app/modules/integrations/ebay/routes/ebay_best_offer_routes.py`
- `backend/app/modules/integrations/ebay/routes/ebay_oauth_routes.py`
- `backend/app/modules/integrations/ebay/schemas/best_offer_schemas.py`
- `backend/app/modules/integrations/ebay/schemas/oauth_schemas.py`
- `backend/app/modules/integrations/ebay/services/ebay_best_offer_action_service.py`
- `backend/app/modules/integrations/ebay/services/ebay_best_offer_query_service.py`
- `backend/app/modules/integrations/ebay/services/ebay_best_offer_sync_service.py`
- `backend/app/modules/integrations/ebay/services/ebay_negotiation_service.py`
- `backend/app/modules/integrations/ebay/services/ebay_offer_validation.py`
- `backend/app/services/ebay_api_usage_service.py`
- `backend/app/services/ebay_best_offer_auto_sync_service.py`
- `backend/app/services/ebay_best_offer_job_service.py`
- `backend/app/services/ebay_best_offer_lock.py`
- `backend/app/services/ebay_best_offer_worker.py`
- `backend/requirements-dev.txt`
- `backend/tests/test_ebay_best_offers.py`
- `backend/tests/test_ebay_best_offers_postgres.py`
- `frontend/src/pages/ebay_accounts/ebay_accounts.css`
- `frontend/src/pages/ebay_accounts/ebay_accounts.jsx`
- `frontend/src/pages/offer_management/BestOfferActionDialog.jsx`
- `frontend/src/pages/offer_management/BestOfferCard.jsx`
- `frontend/src/pages/offer_management/BestOfferConfig.jsx`
- `frontend/src/pages/offer_management/CurrentOffers.jsx`
- `frontend/src/pages/offer_management/bestOfferFormat.js`
- `frontend/src/pages/offer_management/best_offers.css`
- `frontend/src/pages/offer_management/offer_management.jsx`
- `frontend/src/services/ebayBestOfferApi.js`


### OAuth refresh scope correction (2026-09-28)

Token refresh now omits the optional scope parameter, preserving the account's original consent grant. This replaces the Trading/expanded/legacy scope retry chain, avoiding predictable invalid_scope requests for older grants and propagating genuine refresh failures after one request. Successful token operations log at INFO. Adding missing permissions still requires account reconnection and consent; refresh does not grant new permissions. See https://developer.ebay.com/develop/guides/sell/authorization .


### Pending counteroffer discovery gap (2026-09-28)

Live Marine listing 396535199496 returned BuyerBestOffer Countered (GBP 37) and SellerCounterOffer Pending (GBP 92.14) through listing-specific All. Account-wide Active returned no offers, including with UK SiteID and omitted explicit status filter. GetItem confirmed Marine's seller identity. The two negotiation records were imported under that verified role; latest buyer/item selection displays the pending GBP 92.14 counteroffer.

Known open/waiting snapshot members now remain visible until a successful due listing-specific check establishes an empty or terminal outcome. This prevents pending counteroffers from disappearing during listing backoff. Reconciliation continues for these known listings without a broad historical sweep. Newly created pending offers omitted by account-wide discovery remain a coverage gap; this change does not provide a separate discovery feed.


### Automatic event-driven discovery (2026-09-28)

Manual item imports do not provide discovery. ACES now has an OFFER_ACTIVITY webhook, destination/subscription setup endpoints, optional expanded consent, and Config controls for each account. The direct production getTopic/OFFER_ACTIVITY response returned ENABLED with sell.offer/buy.offer scopes even though getTopics omitted the topic. Existing grants must receive fresh seller consent; refresh cannot expand permissions.

A signed event identifies the account, offer and item. ECC/SHA1 signature verification follows the eBay SDK protocol, and account identity must match seller/buyer data. Delivery is deduplicated under the account lock and persisted as an EBAY_OFFER_ACTIVITY SyncLog. Normal sync consumes at most 25 pending event rows per account, uses listing-specific All, and accepts a missing provider Role only from the verified event's account identity. Events wake ordinary backoff without bypassing provider error backoff. Provider failures retain pending events. Completed/expired records stay in history; no financial actions are sent by event processing. New-event discovery does not depend on conversation messages or a preloaded item ID.

Activation: deploy/restart this backend at PUBLIC_BACKEND_URL; for each account use Config -> Authorize offer access, complete matching eBay consent, then Enable offer activity. Ensure sell.offer and commerce.notification.subscription are available in the eBay application keyset. Keep automatic sync enabled or manually sync to consume events. The webhook path is /api/v1/integrations/ebay/best-offers/activity/{account_id}. Challenge uses the persisted destination endpoint and verification token. Event subscriptions are per account and not created automatically until setup is invoked. No migration is needed.

This feed receives future delivered events. It does not retroactively enumerate pending offers that existed before subscription. Active discovery and known-offer reconciliation remain enabled. Complete backfill is still limited by the observed empty Trading discovery and incomplete large-account listing summaries.

References: https://developer.ebay.com/develop/api/buy/notification_events and https://github.com/eBay/event-notification-nodejs-sdk/blob/main/lib/validator.js .


Seller offer authorization requests sell.offer and commerce.notification.subscription only. buy.offer is excluded because the integration discovers buyer offers received on seller listings, rather than subscribing to buyer-side activity.
# Current negotiation visibility and direction

Current offers rank against published current steps and stored terminal steps before applying snapshot membership. A newer verified step for the same item and buyer, including a step seen through another managed account, suppresses older current rows. Unpublished open rows from failed scans do not replace the last complete snapshot. Provider creation time takes precedence over offer ID when ordering steps. Closed steps stay available in saved history.

The card labels the importing account as "Synced account". Offer direction is derived from the provider offer type and verified buyer/seller identities; the selling account can send a seller counteroffer to the buyer. Unknown identities remain explicit rather than being inferred from the account name.
