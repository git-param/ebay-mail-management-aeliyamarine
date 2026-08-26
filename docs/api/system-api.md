# System API Reference

The ACES FastAPI application mounts domain routers below `/api/v1`; `/health` is mounted at the application root. The tables use the required format: API endpoint, response structure, and what it does.

## Response Structure Guide

The endpoint tables name the exact OpenAPI response model where one exists. Important model families are summarized here:

| Structure | Important fields |
|---|---|
| `TokenResponse` | `access_token`, `refresh_token`, `token_type`, `expires_in`, `user` |
| `UserResponse` | User identity/profile, role, permissions, category assignments, active/deleted state, timestamps |
| `EbayAccountResponse` | Account identity, username/store, environment, connection/sync state, token expiry metadata, timestamps; token values are not returned |
| `CategoryResponse` | Category identity, name/description/color, active state, keywords, assigned users, timestamps |
| `ConversationPageResponse` | `items: ConversationSummaryResponse[]`, `total`, `limit`, `offset` |
| `ConversationDetailResponse` | Conversation summary plus `messages`, `offers`, `assignments`, `notes`, product context, and order context |
| `MessageResponse` | Message identity, sender/recipient, body, direction/read state, timestamps, attachments, offer flags |
| `NotificationPageResponse` | Notification items and pagination/unread totals |
| `AnalyticsDashboardResponse` | KPI totals, response-time/SLA metrics, trends, and grouped agent/category/account analytics |
| `AuditLogPageResponse` | Audit items plus `total`, `limit`, and `offset` |
| `File` / `Spreadsheet` | Binary download with `Content-Disposition`; no JSON response body |
| `204 No Content` | Successful mutation with an empty response body |

For every field and validation rule, use the live schema at `/openapi.json` or `/docs`.

## Health

| API endpoint | Response structure | What it does |
|---|---|---|
| `GET /health` | `{"status": "ok"}` | Confirms that the FastAPI process is running. It does not perform a database or eBay health probe. |

## Authentication

| API endpoint | Response structure | What it does |
|---|---|---|
| `POST /api/v1/auth/login` | `TokenResponse` | Authenticates email/password credentials, creates access and refresh tokens, and sets auth cookies. |
| `POST /api/v1/auth/refresh` | `TokenResponse` | Rotates a valid refresh token and issues a new authenticated session. |
| `GET /api/v1/auth/me` | `TokenResponse` with the current `user`; token strings are omitted | Returns the user represented by the current access token. |
| `POST /api/v1/auth/logout` | `{"message": string}` | Revokes the refresh token and clears authentication cookies. |
| `POST /api/v1/auth/forgot-password` | `{"message": string}` | Starts password reset without revealing whether an email is registered. |
| `POST /api/v1/auth/reset-password` | `{"message": string}` | Validates a reset token and replaces the user's password. |

## Users

| API endpoint | Response structure | What it does |
|---|---|---|
| `GET /api/v1/users` | `UserResponse[]` | Lists users visible to the current user. |
| `POST /api/v1/users` | `UserResponse` (`201`) | Creates a user and assigns profile/role data. |
| `GET /api/v1/users/{user_id}` | `UserResponse` | Returns one user. |
| `PUT /api/v1/users/{user_id}` | `UserResponse` | Replaces editable user profile, role, and account fields. |
| `PATCH /api/v1/users/{user_id}/activate` | `UserResponse` | Activates a user account. |
| `PATCH /api/v1/users/{user_id}/deactivate` | `UserResponse` | Deactivates a user and prevents normal access. |
| `DELETE /api/v1/users/{user_id}` | `204 No Content` | Soft-deletes a user where allowed by policy. |
| `POST /api/v1/users/{user_id}/reset-password` | `{message: string, temporary_password?: string}` | Performs an administrator-initiated password reset. |

## eBay Account Records

These endpoints manage local seller-account records. OAuth and synchronization controls are listed under [eBay Integration Controls](#ebay-integration-controls).

| API endpoint | Response structure | What it does |
|---|---|---|
| `GET /api/v1/ebay-accounts` | `EbayAccountResponse[]` | Lists configured seller accounts. |
| `POST /api/v1/ebay-accounts` | `EbayAccountResponse` (`201`) | Creates a pending seller-account record before OAuth connection. |
| `GET /api/v1/ebay-accounts/{account_id}` | `EbayAccountResponse` | Returns one configured seller account. |
| `PUT /api/v1/ebay-accounts/{account_id}` | `EbayAccountResponse` | Updates account metadata and environment settings. |
| `PATCH /api/v1/ebay-accounts/{account_id}/activate` | `EbayAccountResponse` | Enables the account for use and synchronization. |
| `PATCH /api/v1/ebay-accounts/{account_id}/deactivate` | `EbayAccountResponse` | Disables the account without removing synchronized data. |
| `DELETE /api/v1/ebay-accounts/{account_id}` | `{"message": string}` | Deletes an account when repository rules allow it. |

## Categories

| API endpoint | Response structure | What it does |
|---|---|---|
| `GET /api/v1/categories` | `CategoryResponse[]` | Lists conversation categories in the caller's scope. |
| `POST /api/v1/categories` | `CategoryResponse` (`201`) | Creates a category. |
| `GET /api/v1/categories/{category_id}` | `CategoryResponse` | Returns a category, keywords, and assignments. |
| `PUT /api/v1/categories/{category_id}` | `CategoryResponse` | Updates a category. |
| `PUT /api/v1/categories/users/{user_id}/assignments` | `CategoryResponse[]` | Replaces a user's category assignments. |
| `PATCH /api/v1/categories/{category_id}/activate` | `CategoryResponse` | Activates a category. |
| `PATCH /api/v1/categories/{category_id}/deactivate` | `CategoryResponse` | Deactivates a category. |
| `DELETE /api/v1/categories/{category_id}` | `{"message": string}` | Deletes a category when it is safe to do so. |
| `POST /api/v1/categories/{category_id}/keywords` | `CategoryKeywordResponse` (`201`) | Adds an automatic-classification keyword to a category. |
| `DELETE /api/v1/categories/{category_id}/keywords/{keyword_id}` | `{"message": string}` | Removes a category keyword. |

## Conversations and Inbox

| API endpoint | Response structure | What it does |
|---|---|---|
| `POST /api/v1/conversations/translate` | `{translated_text: string, detected_language: string|null}` | Translates supplied text through LibreTranslate without persisting the text. |
| `GET /api/v1/conversations` | `ConversationPageResponse` | Searches, filters, sorts, and paginates inbox conversations using caller visibility rules. |
| `GET /api/v1/conversations/attachments/{stored_name}` | `File` | Downloads an authenticated locally stored reply attachment. |
| `GET /api/v1/conversations/public/attachments/{attachment_id}/download` | `File` | Serves a public attachment URL used for provider media delivery. |
| `GET /api/v1/conversations/{conversation_id}` | `ConversationDetailResponse` | Returns the full thread plus assignment, notes, offer, product, and order context. |
| `PATCH /api/v1/conversations/{conversation_id}/order` | `ConversationDetailResponse` | Selects or clears the order linked to an ambiguous conversation. |
| `GET /api/v1/conversations/{conversation_id}/context` | `ConversationProductContextResponse|null` | Returns listing/product context and action availability. |
| `GET /api/v1/conversations/{conversation_id}/messages` | `MessageResponse[]` | Returns messages for one visible conversation. |
| `POST /api/v1/conversations/{conversation_id}/reply/validate` | `{valid: boolean, violations: string[]}` | Validates reply content against business rules without sending it. |
| `POST /api/v1/conversations/{conversation_id}/reply` | `MessageResponse` | Sends a text or multipart reply through eBay and stores the outbound message/attachments. |
| `POST /api/v1/conversations/{conversation_id}/assign` | `ConversationAssignmentResponse` | Assigns the conversation to a user and closes the previous active assignment. |
| `POST /api/v1/conversations/{conversation_id}/notes` | `ConversationNoteResponse` | Adds an internal note. |
| `GET /api/v1/conversations/{conversation_id}/notes` | `ConversationNoteResponse[]` | Lists internal notes in the thread. |
| `PATCH /api/v1/conversations/{conversation_id}/notes/{note_id}` | `ConversationNoteResponse` | Edits an authorized internal note. |
| `DELETE /api/v1/conversations/{conversation_id}/notes/{note_id}` | `204 No Content` | Deletes an authorized internal note. |
| `PATCH /api/v1/conversations/{conversation_id}/status` | `ConversationDetailResponse` | Changes the local workflow status and records optional context. |
| `PATCH /api/v1/conversations/{conversation_id}/category` | `ConversationDetailResponse` | Manually sets or clears the category. |
| `POST /api/v1/conversations/bulk-update` | `{updated_count, assignment_count, skipped_count, message}` | Applies status, category, or assignment changes to up to 500 conversations. |

## Synchronized Offers

| API endpoint | Response structure | What it does |
|---|---|---|
| `POST /api/v1/offers/sync/account/{account_id}` | `{status: "queued", account_id: string, source: string}` (`202`) | Queues Trading API Best Offer synchronization for one seller account. |
| `GET /api/v1/offers/conversation/{conversation_id}` | `OfferResponse[]` | Returns normalized offer events/cards linked to a visible conversation. |

## Notifications

| API endpoint | Response structure | What it does |
|---|---|---|
| `GET /api/v1/notifications` | `NotificationPageResponse` | Lists the current user's notifications with paging and unread filtering. |
| `PATCH /api/v1/notifications/read` | `{updated_count: integer}` | Marks all current-user notifications as read. |
| `PATCH /api/v1/notifications/{notification_id}/read` | `{updated_count: integer}` | Marks one notification as read. |
| `DELETE /api/v1/notifications` | `{deleted_count: integer}` | Deletes all current-user notifications. |
| `DELETE /api/v1/notifications/{notification_id}` | `{deleted_count: integer}` | Deletes one current-user notification. |

## Audit and Analytics

| API endpoint | Response structure | What it does |
|---|---|---|
| `GET /api/v1/audit-logs` | `AuditLogPageResponse` | Filters and paginates immutable operational/security audit events. |
| `GET /api/v1/audit-logs/export` | `Spreadsheet` | Exports the authorized audit-log selection. |
| `GET /api/v1/analytics/dashboard` | `AnalyticsDashboardResponse` | Calculates dashboard KPIs and grouped performance metrics for a date/filter range. |
| `GET /api/v1/analytics/dashboard/export` | `Spreadsheet` | Exports dashboard analytics for the selected filters. |

## Reply Templates and Permissions

| API endpoint | Response structure | What it does |
|---|---|---|
| `GET /api/v1/templates` | `ReplyTemplateResponse[]` | Lists visible reply templates, optionally including inactive templates. |
| `POST /api/v1/templates` | `ReplyTemplateResponse` (`201`) | Creates a reply template. |
| `PUT /api/v1/templates/{template_id}` | `ReplyTemplateResponse` | Updates a reply template. |
| `DELETE /api/v1/templates/{template_id}` | `204 No Content` | Deletes a reply template. |
| `GET /api/v1/templates/roles/{role_id}/permissions` | `PermissionResponse[]` | Lists permissions assigned to a role. |
| `PUT /api/v1/templates/roles/{role_id}/permissions` | `PermissionResponse[]` | Replaces a role's permission assignments. |

## Message Types and Reports

| API endpoint | Response structure | What it does |
|---|---|---|
| `GET /api/v1/message-types` | `MessageTypeResponse[]` | Returns the message-type hierarchy, optionally including deleted nodes. |
| `GET /api/v1/message-types/tree` | `MessageTypeResponse[]` | Returns the active hierarchy for dropdowns. |
| `POST /api/v1/message-types` | `MessageTypeResponse` | Creates a message type or subtype. |
| `PUT /api/v1/message-types/{item_id}` | `MessageTypeResponse` | Updates a message type. |
| `DELETE /api/v1/message-types/{item_id}` | `{id, is_active, is_deleted}` | Soft-deletes a message type. |
| `PATCH /api/v1/message-types/{item_id}/status` | `{id, is_active, is_deleted}` | Changes active/deleted state. |
| `GET /api/v1/reports/message-types` | `{items: object[], total: integer, limit: integer, offset: integer}` | Filters and paginates conversation message-type classifications. |
| `GET /api/v1/reports/message-types/export` | `Spreadsheet` | Exports the selected message-type report. |

## Cross-Platform SKU Search

| API endpoint | Response structure | What it does |
|---|---|---|
| `GET /api/v1/search-sku` | `CrossPlatformSearchResponse` | Searches configured external inventory sources for a SKU and returns normalized platform results. |

## Offer Management

This module tracks operational follow-up entries; it is separate from synchronized eBay offer cards.

| API endpoint | Response structure | What it does |
|---|---|---|
| `POST /api/v1/offer-management` | `OfferEntryResponse` | Creates an operational offer-management entry. |
| `GET /api/v1/offer-management` | `OfferEntryListResponse` | Filters and paginates operational offer entries. |
| `GET /api/v1/offer-management/lookup` | `OfferLookupResponse` | Looks up listing/account data for entry creation. |
| `GET /api/v1/offer-management/summary` | `OfferSummaryResponse` | Returns status/follow-up summary totals. |
| `GET /api/v1/offer-management/lookups` | `{users: object[], accounts: object[], statuses: string[], ...}` | Returns dropdown/reference values used by the module. |
| `GET /api/v1/offer-management/export` | `Spreadsheet` | Exports filtered offer-management entries. |
| `GET /api/v1/offer-management/{entry_id}` | `OfferEntryResponse` | Returns one entry. |
| `PUT /api/v1/offer-management/{entry_id}` | `OfferEntryResponse` | Updates one entry and records history. |
| `DELETE /api/v1/offer-management/{entry_id}` | `204 No Content` | Deletes one entry. |
| `POST /api/v1/offer-management/bulk-delete` | `OfferBulkDeleteResponse` | Deletes a selected set of entries and reports the result. |
| `GET /api/v1/offer-management/{entry_id}/history` | `OfferEntryHistoryResponse[]` | Returns the entry's change history. |

## Sold Posting

| API endpoint | Response structure | What it does |
|---|---|---|
| `GET /api/v1/sold-posting/orders` | `SoldPostingListResponse` | Filters and paginates synchronized sold line items for posting work. |
| `GET /api/v1/sold-posting/orders/{order_id}` | `SoldPostingOrderDetail` | Returns order and line-item details. |
| `PUT /api/v1/sold-posting/line-items/{line_item_record_id}` | `SoldPostingRow` | Updates editable posting state for a line item. |
| `POST /api/v1/sold-posting/line-items/{line_item_record_id}/copied` | `SoldPostingRow` | Marks a line item as copied/processed. |
| `POST /api/v1/sold-posting/sync` | `SoldPostingSyncResponse` | Starts or runs order synchronization for sold-posting data. |
| `GET /api/v1/sold-posting/sync-status` | `{running: boolean, ...sync metadata}` | Returns current sold-posting synchronization state. |
| `GET /api/v1/sold-posting/filter-options` | `SoldPostingFilterOptions` | Returns values for account/status/date filtering. |

## PMS

| API endpoint | Response structure | What it does |
|---|---|---|
| `GET /api/v1/pms/config` | `PmsMetricConfigListResponse` | Lists weighted PMS metric definitions. |
| `POST /api/v1/pms/config` | `PmsMetricConfigResponse` | Creates a PMS metric. |
| `PUT /api/v1/pms/config/{config_id}` | `PmsMetricConfigResponse` | Updates a PMS metric. |
| `DELETE /api/v1/pms/config/{config_id}` | `204 No Content` | Deletes a PMS metric configuration. |
| `GET /api/v1/pms/monthly/available-periods` | `{items: [{year, month, label}], ...}` | Lists periods with monthly PMS data. |
| `GET /api/v1/pms/monthly` | `PmsMonthlyTableResponse` | Returns the monthly PMS table across authorized users. |
| `GET /api/v1/pms/monthly/target-achievement` | `PmsTargetAchievementResponse` | Returns target-achievement configuration/data for a period. |
| `PUT /api/v1/pms/monthly/target-achievement` | `PmsTargetAchievementResponse` | Updates target-achievement data. |
| `GET /api/v1/pms/monthly/export` | `Spreadsheet` | Exports one or more monthly PMS tables. |
| `GET /api/v1/pms/monthly/{user_id}` | `PmsMonthlyRecordResponse` | Returns one user's monthly PMS record. |
| `POST /api/v1/pms/monthly/refresh` | `PmsMonthlyRecordResponse` | Recalculates automatic values for a monthly record. |
| `POST /api/v1/pms/monthly` | `PmsMonthlyRecordResponse` | Creates or updates manually supplied monthly PMS values. |
| `GET /api/v1/pms/history` | `PmsHistoryResponse` | Returns PMS history for an authorized user/range. |
| `GET /api/v1/pms/employee-of-month` | `PmsEmployeeOfMonthResponse` | Resolves or returns the employee-of-month result for a period. |
| `GET /api/v1/pms/employee-of-month/stats` | `PmsEmployeeOfMonthStatsResponse` | Returns supporting employee-of-month statistics. |
| `POST /api/v1/pms/employee-of-month/resolve` | `PmsEmployeeOfMonthResponse` | Manually resolves a tie/selection. |

## Task Management

| API endpoint | Response structure | What it does |
|---|---|---|
| `GET /api/v1/task-management/categories` | `TaskCategoryResponse[]` | Lists task categories with nested subtasks and child tasks. |
| `POST /api/v1/task-management/categories` | `TaskCategoryResponse` | Creates a task category. |
| `PATCH /api/v1/task-management/categories/{category_id}` | `TaskCategoryResponse` | Updates a task category. |
| `DELETE /api/v1/task-management/categories/{category_id}` | `{"message": string}` | Deletes a task category. |
| `POST /api/v1/task-management/subtasks` | `SubtaskResponse` | Creates a subtask under a category. |
| `PATCH /api/v1/task-management/subtasks/{subtask_id}` | `SubtaskResponse` | Updates a subtask. |
| `DELETE /api/v1/task-management/subtasks/{subtask_id}` | `{"message": string}` | Deletes a subtask. |
| `POST /api/v1/task-management/sub-subtasks` | `SubSubtaskResponse` | Creates a child task under a subtask. |
| `PATCH /api/v1/task-management/sub-subtasks/{sub_subtask_id}` | `SubSubtaskResponse` | Updates a child task. |
| `DELETE /api/v1/task-management/sub-subtasks/{sub_subtask_id}` | `{"message": string}` | Deletes a child task. |
| `GET /api/v1/task-management/assignments` | `UserAssignmentSummary` | Lists one user's assignments and total active quality weight. |
| `POST /api/v1/task-management/assignments` | `AssignmentResponse` | Assigns a subtask or child task to a user. |
| `PATCH /api/v1/task-management/assignments/{assignment_id}` | `AssignmentResponse` | Updates dates, weight, status, or automatic-fetch behavior. |
| `POST /api/v1/task-management/task-assignments` | `UserAssignmentSummary` | Assigns every subtask in one category to a user. |

## Leave Management

| API endpoint | Response structure | What it does |
|---|---|---|
| `GET /api/v1/leave-management/policy` | `LeavePolicyResponse` | Returns the active leave policy. |
| `PUT /api/v1/leave-management/policy` | `LeavePolicyResponse` | Updates leave policy settings. |
| `POST /api/v1/leave-management/requests` | `LeaveRequestResponse` (`201`) | Creates a leave request. |
| `GET /api/v1/leave-management/requests` | `LeaveRequestListResponse` | Filters leave requests visible to the caller. |
| `POST /api/v1/leave-management/requests/{request_id}/review` | `LeaveRequestResponse` | Approves/rejects a leave request. |
| `POST /api/v1/leave-management/requests/{request_id}/cancel` | `LeaveRequestResponse` | Cancels an eligible leave request. |
| `GET /api/v1/leave-management/balances` | `LeaveBalanceResponse[]` | Returns monthly leave balances in the authorized scope. |
| `GET /api/v1/leave-management/admin-summary` | `LeaveAdminSummaryRow[]` | Returns the administrative monthly leave summary. |
| `PUT /api/v1/leave-management/admin-summary` | `LeaveAdminSummaryRow[]` | Updates administrative summary adjustments. |
| `GET /api/v1/leave-management/carry-forward` | `LeaveCarryForwardResponse` | Returns one user's carry-forward value. |
| `PUT /api/v1/leave-management/carry-forward` | `LeaveCarryForwardResponse` | Updates carry-forward leave. |
| `GET /api/v1/leave-management/balances/me` | `LeaveBalanceResponse` | Returns the current user's balance for a month. |
| `GET /api/v1/leave-management/impact` | `LeaveImpactResponse` | Calculates leave impact used by PMS. |

## Daily Task Entry

The existing route prefix intentionally uses camel case: `/dailyEntry`.

| API endpoint | Response structure | What it does |
|---|---|---|
| `GET /api/v1/dailyEntry/draft` | `DailyEntryDraftResponse` | Builds a draft entry and applicable limits for a user/date. |
| `GET /api/v1/dailyEntry/daily-entries/load` | `DailyEntryLoadResponse` | Loads all daily-entry rows for a user/date. |
| `POST /api/v1/dailyEntry/daily-entries/upload` | `DailyEntryUploadResponse` | Validates and saves a batch of daily entries. |
| `POST /api/v1/dailyEntry/entries` | `DailyEntryResponse` | Creates or updates one daily task entry. |
| `GET /api/v1/dailyEntry/entries` | `DailyEntryListResponse` | Lists daily entries for a date range/user. |
| `GET /api/v1/dailyEntry/sla-review` | `DailyEntrySLAReviewResponse` | Returns administrator SLA score-review details. |

## Application Configuration

| API endpoint | Response structure | What it does |
|---|---|---|
| `GET /api/v1/config` | `ConfigSettingResponse[]` | Lists editable runtime application settings. |
| `PUT /api/v1/config` | `ConfigSettingResponse[]` | Updates editable application settings. |
| `GET /api/v1/config/account-sync` | `AccountSyncStateResponse[]` | Lists per-account synchronization controls/state. |
| `PUT /api/v1/config/account-sync` | `{message: string, ...state}` | Updates account synchronization controls. |
| `DELETE /api/v1/config/conversation-data` | `{message: string, deleted_counts?: object}` | Deletes synchronized conversation data according to the administrative request. |

## eBay Integration Controls

These are ACES endpoints. The external eBay endpoints they invoke are documented in [ebay-api.md](ebay-api.md).

| API endpoint | Response structure | What it does |
|---|---|---|
| `POST /api/v1/integrations/ebay/connect` | `{authorization_url: string, state: string}` | Creates OAuth state and returns the eBay authorization URL. |
| `POST /api/v1/integrations/ebay/manual-callback` | `EbayOAuthCallbackResponse` | Completes OAuth using a manually supplied code/state pair. |
| `GET /api/v1/integrations/ebay/callback` | `307 Redirect` | Handles eBay's browser callback, stores tokens/identity, and redirects to the frontend. |
| `POST /api/v1/integrations/ebay/refresh-token/{account_id}` | `EbayRefreshTokenResponse` | Refreshes and stores a seller access token. |
| `GET /api/v1/integrations/ebay/test-connection/{account_id}` | `EbayTestConnectionResponse` | Verifies the account token with eBay Identity. |
| `GET /api/v1/integrations/ebay/api-usage` | `EbayApiUsageListResponse` | Returns tracked per-account/per-API call usage. |
| `GET /api/v1/integrations/ebay/auto-sync` | `EbayAutoSyncStatusResponse` | Returns automatic synchronization enabled/interval state. |
| `PATCH /api/v1/integrations/ebay/auto-sync` | `EbayAutoSyncStatusResponse` | Enables/disables automatic synchronization. |
| `POST /api/v1/integrations/ebay/sync/{account_id}` | `EbaySyncResultResponse` | Starts synchronization for one account, optionally with a conversation limit. |
| `POST /api/v1/integrations/ebay/sync-all` | `EbaySyncAllResponse` | Starts synchronization for all active connected accounts. |
| `GET /api/v1/integrations/ebay/sync-status/{sync_log_id}` | `{sync_log_id, account_id, ebay_username, status, records_processed, error_message, timestamps, ...}` | Polls a synchronization run. |
| `POST /api/v1/integrations/ebay/test-conversations/{account_id}` | `{request, response_status_code, response_payload, ...}` | Diagnostic call for an eBay conversation page. |
| `GET /api/v1/integrations/ebay/test-conversation/{account_id}/{conversation_id}` | `{request, response_status_code, response_payload, ...}` | Diagnostic call for one eBay conversation. |

## Source of Truth and Known Router Warning

This reference was checked against `app.openapi()` and the mounted routers. At the time of writing there are 124 unique OpenAPI paths. `backend/app/api/v1/router.py` includes the PMS router and task-management router twice; FastAPI therefore logs duplicate operation-ID warnings during OpenAPI generation. The URL/path map above lists each effective path once.
