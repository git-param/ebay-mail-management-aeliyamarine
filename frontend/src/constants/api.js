/** Central catalog for backend API paths. Query values belong to callers. */
export const API_PREFIX = '/api/v1'
export const API_PROXY_PREFIX = '/api'
export const DEFAULT_BACKEND_URL = 'http://127.0.0.1:8000'

export function getApiBaseUrl() {
  return import.meta.env?.VITE_API_BASE_URL ?? API_PREFIX
}

/** Substitute already-prepared parameters; preserves callers' existing encoding. */
export function apiPath(template, parameters = {}) {
  return template.replace(/\{([a-zA-Z_][a-zA-Z0-9_]*)\}/g, (_, name) => {
    if (!Object.hasOwn(parameters, name) || parameters[name] == null) {
      throw new Error(`Missing API path parameter: ${name}`)
    }
    return String(parameters[name])
  })
}

export const API = Object.freeze({
  ANALYTICS: Object.freeze({
    DASHBOARD: "/analytics/dashboard",
    DASHBOARD_EXPORT: "/analytics/dashboard/export",
  }),

  AUDIT_LOGS: Object.freeze({
    DELETION_PREVIEW: "/audit-logs/deletion-preview",
    ROOT: "/audit-logs",
    FILTERS: "/audit-logs/filters",
    EXPORT: "/audit-logs/export",
  }),

  AUTH: Object.freeze({
    LOGIN: "/auth/login",
    FORGOT_PASSWORD: "/auth/forgot-password",
    RESET_PASSWORD: "/auth/reset-password",
    ME: "/auth/me",
    LOGOUT: "/auth/logout",
    REFRESH: "/auth/refresh",
  }),
  BREAK_MANAGEMENT: Object.freeze({
    STATUS: "/break-management/status",
    START: "/break-management/start",
    END: "/break-management/end",
    HISTORY: "/break-management/history",
    OVERVIEW: "/break-management/overview",
    EMPLOYEES: "/break-management/employees",
    EXPORT: "/break-management/export",
  }),

  CATEGORIES: Object.freeze({
    ROOT: "/categories",
    BY_CATEGORY_ID: "/categories/{categoryId}",
    BY_CATEGORY_ID_ACTIVATE: "/categories/{categoryId}/activate",
    BY_CATEGORY_ID_DEACTIVATE: "/categories/{categoryId}/deactivate",
    BY_CATEGORY_ID_KEYWORDS: "/categories/{categoryId}/keywords",
    BY_CATEGORY_ID_KEYWORDS_BY_KEYWORD_ID: "/categories/{categoryId}/keywords/{keywordId}",
    USERS_BY_USER_ID_ASSIGNMENTS: "/categories/users/{userId}/assignments",
  }),

  CONFIG: Object.freeze({
    ROOT: "/config",
    ACCOUNT_SYNC: "/config/account-sync",
    CONVERSATION_DATA: "/config/conversation-data",
  }),

  CONVERSATIONS: Object.freeze({
    START: "/conversations/start",
    START_VALIDATE: "/conversations/start/validate",
    ROOT: "/conversations",
    BY_CONVERSATION_ID: "/conversations/{conversationId}",
    BY_CONVERSATION_ID_CONTEXT: "/conversations/{conversationId}/context",
    TRANSLATE: "/conversations/translate",
    BY_CONVERSATION_ID_ASSIGN: "/conversations/{conversationId}/assign",
    BULK_UPDATE: "/conversations/bulk-update",
    BY_CONVERSATION_ID_NOTES: "/conversations/{conversationId}/notes",
    BY_CONVERSATION_ID_UNASSIGN: "/conversations/{conversationId}/unassign",
    BY_CONVERSATION_ID_NOTES_BY_NOTE_ID: "/conversations/{conversationId}/notes/{noteId}",
    BY_CONVERSATION_ID_CATEGORY: "/conversations/{conversationId}/category",
    BY_CONVERSATION_ID_STATUS: "/conversations/{conversationId}/status",
    BY_CONVERSATION_ID_REPLY_VALIDATE: "/conversations/{conversationId}/reply/validate",
    BY_CONVERSATION_ID_REPLY: "/conversations/{conversationId}/reply",
  }),

  DAILY_ENTRY: Object.freeze({
    DRAFT: "/dailyEntry/draft",
    ENTRIES: "/dailyEntry/entries",
    DAILY_ENTRIES_LOAD: "/dailyEntry/daily-entries/load",
    DAILY_ENTRIES_UPLOAD: "/dailyEntry/daily-entries/upload",
    DAILY_ENTRIES_DELETE: "/dailyEntry/daily-entries/delete",
    SLA_REVIEW: "/dailyEntry/sla-review",
  }),

  EBAY_ACCOUNTS: Object.freeze({
    ROOT: "/ebay-accounts",
    BY_ACCOUNT_ID: "/ebay-accounts/{accountId}",
    BY_ACCOUNT_ID_ACTIVATE: "/ebay-accounts/{accountId}/activate",
    BY_ACCOUNT_ID_DEACTIVATE: "/ebay-accounts/{accountId}/deactivate",
  }),

  EBAY_INTEGRATION: Object.freeze({
    SYNC_STATUS_BY_SYNC_LOG_ID: "/integrations/ebay/sync-status/{syncLogId}",
    CONNECT: "/integrations/ebay/connect",
    MANUAL_CALLBACK: "/integrations/ebay/manual-callback",
    API_USAGE: "/integrations/ebay/api-usage",
    AUTO_SYNC: "/integrations/ebay/auto-sync",
    SYNC_BY_ACCOUNT_ID: "/integrations/ebay/sync/{accountId}",
    SYNC_ALL: "/integrations/ebay/sync-all",
  }),

  EBAY_BEST_OFFERS: Object.freeze({
    CURRENT: "/integrations/ebay/best-offers/current",
    ACCOUNTS: "/integrations/ebay/best-offers/accounts",
    CONFIG: "/integrations/ebay/best-offers/config",
    SYNC: "/integrations/ebay/best-offers/sync",
    JOBS_BY_ID: "/integrations/ebay/best-offers/jobs/{id}",
    JOBS_BY_ID_CANCEL: "/integrations/ebay/best-offers/jobs/{id}/cancel",
    BY_ID_RESPOND: "/integrations/ebay/best-offers/{id}/respond",
    BY_ID_DONE: "/integrations/ebay/best-offers/{id}/done",
    ACTIVITY_BY_ID_AUTHORIZE: "/integrations/ebay/best-offers/activity/{id}/authorize",
    ACTIVITY_BY_ID_SETUP: "/integrations/ebay/best-offers/activity/{id}/setup",
  }),

  LEAVE_MANAGEMENT: Object.freeze({
    POLICY: "/leave-management/policy",
    REQUESTS: "/leave-management/requests",
    REQUESTS_BY_REQUEST_ID_REVIEW: "/leave-management/requests/{requestId}/review",
    REQUESTS_BY_REQUEST_ID_CANCEL: "/leave-management/requests/{requestId}/cancel",
    BALANCES: "/leave-management/balances",
    ADMIN_SUMMARY: "/leave-management/admin-summary",
    CARRY_FORWARD: "/leave-management/carry-forward",
    BALANCES_ME: "/leave-management/balances/me",
  }),

  MESSAGE_TYPES: Object.freeze({
    TREE: "/message-types/tree",
    ROOT: "/message-types",
    BY_ID: "/message-types/{id}",
    BY_ID_STATUS: "/message-types/{id}/status",
  }),

  REPORTS: Object.freeze({
    MESSAGE_TYPES: "/reports/message-types",
    MESSAGE_TYPES_EXPORT: "/reports/message-types/export",
  }),

  NOTIFICATIONS: Object.freeze({
    ROOT: "/notifications",
    READ: "/notifications/read",
    BY_NOTIFICATION_ID: "/notifications/{notificationId}",
  }),

  OFFER_MANAGEMENT: Object.freeze({
    ROOT: "/offer-management",
    SUMMARY: "/offer-management/summary",
    LOOKUPS: "/offer-management/lookups",
    LOOKUP: "/offer-management/lookup",
    DUPLICATE_CHECK: "/offer-management/duplicate-check",
    BY_ID: "/offer-management/{id}",
    BULK_DELETE: "/offer-management/bulk-delete",
    IMPORT_EXCEL: "/offer-management/import-excel",
    BY_ID_HISTORY: "/offer-management/{id}/history",
    EXPORT: "/offer-management/export",
  }),

  PMS: Object.freeze({
    CONFIG: "/pms/config",
    CONFIG_BY_CONFIG_ID: "/pms/config/{configId}",
    MONTHLY: "/pms/monthly",
    MONTHLY_TARGET_ACHIEVEMENT: "/pms/monthly/target-achievement",
    MONTHLY_AVAILABLE_PERIODS: "/pms/monthly/available-periods",
    MONTHLY_EXPORT: "/pms/monthly/export",
    MONTHLY_BY_USER_ID: "/pms/monthly/{userId}",
    MONTHLY_REFRESH: "/pms/monthly/refresh",
    HISTORY: "/pms/history",
    EMPLOYEE_OF_MONTH: "/pms/employee-of-month",
    EMPLOYEE_OF_MONTH_STATS: "/pms/employee-of-month/stats",
    EMPLOYEE_OF_MONTH_RESOLVE: "/pms/employee-of-month/resolve",
  }),

  SEARCH_SKU: Object.freeze({
    ROOT: "/search-sku",
  }),

  SOLD_POSTING: Object.freeze({
    ORDER_CONVERSATION: "/sold-posting/orders/{orderId}/conversation",
    ORDERS: "/sold-posting/orders",
    ORDERS_BY_ORDER_ID: "/sold-posting/orders/{orderId}",
    FILTER_OPTIONS: "/sold-posting/filter-options",
    SYNC: "/sold-posting/sync",
    LINE_ITEMS_BY_LINE_ITEM_RECORD_ID: "/sold-posting/line-items/{lineItemRecordId}",
    LINE_ITEMS_BY_LINE_ITEM_RECORD_ID_COPIED: "/sold-posting/line-items/{lineItemRecordId}/copied",
  }),

  TASK_MANAGEMENT: Object.freeze({
    CATEGORIES: "/task-management/categories",
    CATEGORIES_BY_ID: "/task-management/categories/{id}",
    SUBTASKS: "/task-management/subtasks",
    SUBTASKS_BY_ID: "/task-management/subtasks/{id}",
    SUB_SUBTASKS: "/task-management/sub-subtasks",
    SUB_SUBTASKS_BY_ID: "/task-management/sub-subtasks/{id}",
    ASSIGNMENTS: "/task-management/assignments",
    ASSIGNMENTS_BY_ID: "/task-management/assignments/{id}",
    TASK_ASSIGNMENTS: "/task-management/task-assignments",
  }),

  TEMPLATES: Object.freeze({
    ROOT: "/templates",
    BY_TEMPLATE_ID: "/templates/{templateId}",
    CATEGORIES: "/templates/categories",
    CATEGORIES_BY_CATEGORY_ID: "/templates/categories/{categoryId}",
    ROLES_BY_ROLE_ID_PERMISSIONS: "/templates/roles/{roleId}/permissions",
  }),

  USERS: Object.freeze({
    ROOT: "/users",
    BY_USER_ID: "/users/{userId}",
    BY_USER_ID_ACTIVATE: "/users/{userId}/activate",
    BY_USER_ID_DEACTIVATE: "/users/{userId}/deactivate",
    BY_USER_ID_RESET_PASSWORD: "/users/{userId}/reset-password",
  }),
})
