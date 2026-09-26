# eBay Best Offer implementation report ? 2026-09-26

## Scope expanded: buyer, seller, active and historical offers

### Latest-change synchronization and clearer results

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
