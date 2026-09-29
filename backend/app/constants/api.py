"""API endpoint catalog. Keep route paths and provider URLs here.

Dynamic identifiers and query values are supplied by callers with str.format().
Environment variables may override deployment-specific base URLs.
"""


class ApiPrefixes:
    AUTH = '/auth'
    USERS = '/users'
    EBAY_ACCOUNTS = '/ebay-accounts'
    CATEGORIES = '/categories'
    CONVERSATIONS = '/conversations'
    OFFERS = '/offers'
    NOTIFICATIONS = '/notifications'
    AUDIT_LOGS = '/audit-logs'
    ANALYTICS = '/analytics'
    TEMPLATES = '/templates'
    MESSAGE_TYPES = '/message-types'
    REPORTS = '/reports'
    OFFER_MANAGEMENT = '/offer-management'
    SOLD_POSTING = '/sold-posting'
    PMS = '/pms'
    TASK_MANAGEMENT = '/task-management'
    LEAVE_MANAGEMENT = '/leave-management'
    BREAK_MANAGEMENT = '/break-management'
    DAILY_ENTRY = '/dailyEntry'
    CONFIG = '/config'
    INTEGRATIONS_EBAY = '/integrations/ebay'
    INTEGRATIONS_EBAY_BEST_OFFERS = '/integrations/ebay/best-offers'
    API_V1 = '/api/v1'


class AnalyticsRoutes:
    DASHBOARD = '/dashboard'
    DASHBOARD_EXPORT = '/dashboard/export'


class AuditLogsRoutes:
    FILTERS = '/filters'
    ROOT = ''
    EXPORT = '/export'
    DELETION_PREVIEW = '/deletion-preview'


class AuthRoutes:
    LOGIN = '/login'
    REFRESH = '/refresh'
    ME = '/me'
    LOGOUT = '/logout'
    FORGOT_PASSWORD = '/forgot-password'
    RESET_PASSWORD = '/reset-password'


class CategoriesRoutes:
    ROOT = ''
    BY_CATEGORY_ID = '/{category_id}'
    USERS_BY_USER_ID_ASSIGNMENTS = '/users/{user_id}/assignments'
    BY_CATEGORY_ID_ACTIVATE = '/{category_id}/activate'
    BY_CATEGORY_ID_DEACTIVATE = '/{category_id}/deactivate'
    BY_CATEGORY_ID_KEYWORDS = '/{category_id}/keywords'
    BY_CATEGORY_ID_KEYWORDS_BY_KEYWORD_ID = '/{category_id}/keywords/{keyword_id}'


class ConversationsRoutes:
    TRANSLATE = '/translate'
    ROOT = ''
    ATTACHMENTS_BY_STORED_NAME = '/attachments/{stored_name}'
    PUBLIC_ATTACHMENTS_BY_ATTACHMENT_ID_DOWNLOAD = '/public/attachments/{attachment_id}/download'
    BY_CONVERSATION_ID = '/{conversation_id}'
    BY_CONVERSATION_ID_ORDER = '/{conversation_id}/order'
    BY_CONVERSATION_ID_CONTEXT = '/{conversation_id}/context'
    BY_CONVERSATION_ID_MESSAGES = '/{conversation_id}/messages'
    BY_CONVERSATION_ID_REPLY_VALIDATE = '/{conversation_id}/reply/validate'
    BY_CONVERSATION_ID_REPLY = '/{conversation_id}/reply'
    BY_CONVERSATION_ID_ASSIGN = '/{conversation_id}/assign'
    BY_CONVERSATION_ID_UNASSIGN = '/{conversation_id}/unassign'
    BY_CONVERSATION_ID_NOTES = '/{conversation_id}/notes'
    BY_CONVERSATION_ID_NOTES_BY_NOTE_ID = '/{conversation_id}/notes/{note_id}'
    BY_CONVERSATION_ID_STATUS = '/{conversation_id}/status'
    BY_CONVERSATION_ID_CATEGORY = '/{conversation_id}/category'
    BULK_UPDATE = '/bulk-update'


class EbayAccountsRoutes:
    ROOT = ''
    BY_ACCOUNT_ID = '/{account_id}'
    BY_ACCOUNT_ID_ACTIVATE = '/{account_id}/activate'
    BY_ACCOUNT_ID_DEACTIVATE = '/{account_id}/deactivate'


class MessageTypesRoutes:
    ROOT = ''
    TREE = '/tree'
    BY_ITEM_ID = '/{item_id}'
    BY_ITEM_ID_STATUS = '/{item_id}/status'


class MessageReportsRoutes:
    MESSAGE_TYPES = '/message-types'
    MESSAGE_TYPES_EXPORT = '/message-types/export'


class NotificationsRoutes:
    ROOT = ''
    READ = '/read'
    BY_NOTIFICATION_ID_READ = '/{notification_id}/read'
    BY_NOTIFICATION_ID = '/{notification_id}'


class OffersRoutes:
    SYNC_ACCOUNT_BY_ACCOUNT_ID = '/sync/account/{account_id}'
    CONVERSATION_BY_CONVERSATION_ID = '/conversation/{conversation_id}'


class TemplatesRoutes:
    ROOT = ''
    BY_TEMPLATE_ID = '/{template_id}'
    CATEGORIES = '/categories'
    CATEGORIES_BY_CATEGORY_ID = '/categories/{category_id}'
    ROLES_BY_ROLE_ID_PERMISSIONS = '/roles/{role_id}/permissions'


class UsersRoutes:
    ROOT = ''
    BY_USER_ID = '/{user_id}'
    BY_USER_ID_ACTIVATE = '/{user_id}/activate'
    BY_USER_ID_DEACTIVATE = '/{user_id}/deactivate'
    BY_USER_ID_RESET_PASSWORD = '/{user_id}/reset-password'


class HealthRoutes:
    HEALTH = '/health'


class BreakManagementRoutes:
    STATUS = '/status'
    START = '/start'
    END = '/end'
    HISTORY = '/history'
    OVERVIEW = '/overview'
    EMPLOYEES = '/employees'
    EXPORT = '/export'


class ConfigManagementRoutes:
    ROOT = ''
    ACCOUNT_SYNC = '/account-sync'
    CONVERSATION_DATA = '/conversation-data'


class DailyTaskEntryRoutes:
    DRAFT = '/draft'
    DAILY_ENTRIES_LOAD = '/daily-entries/load'
    DAILY_ENTRIES_UPLOAD = '/daily-entries/upload'
    DAILY_ENTRIES_DELETE = '/daily-entries/delete'
    ENTRIES = '/entries'
    SLA_REVIEW = '/sla-review'


class EbayBestOfferRoutes:
    CURRENT = '/current'
    ACCOUNTS = '/accounts'
    CONFIG = '/config'
    SYNC = '/sync'
    JOBS_BY_JOB_ID = '/jobs/{job_id}'
    BY_OFFER_ID_RESPOND = '/{offer_id}/respond'
    JOBS_BY_JOB_ID_CANCEL = '/jobs/{job_id}/cancel'
    ACTIVITY_BY_ACCOUNT_ID = '/activity/{account_id}'
    ACTIVITY_BY_ACCOUNT_ID_AUTHORIZE = '/activity/{account_id}/authorize'
    ACTIVITY_BY_ACCOUNT_ID_SETUP = '/activity/{account_id}/setup'


class EbayOAuthRoutes:
    CONNECT = '/connect'
    MANUAL_CALLBACK = '/manual-callback'
    CALLBACK = '/callback'
    REFRESH_TOKEN_BY_ACCOUNT_ID = '/refresh-token/{account_id}'
    TEST_CONNECTION_BY_ACCOUNT_ID = '/test-connection/{account_id}'
    API_USAGE = '/api-usage'
    AUTO_SYNC = '/auto-sync'
    SYNC_BY_ACCOUNT_ID = '/sync/{account_id}'
    SYNC_ALL = '/sync-all'
    SYNC_STATUS_BY_SYNC_LOG_ID = '/sync-status/{sync_log_id}'
    TEST_CONVERSATIONS_BY_ACCOUNT_ID = '/test-conversations/{account_id}'
    TEST_CONVERSATION_BY_ACCOUNT_ID_BY_CONVERSATION_ID = '/test-conversation/{account_id}/{conversation_id}'


class LeaveManagementRoutes:
    POLICY = '/policy'
    REQUESTS = '/requests'
    REQUESTS_BY_REQUEST_ID_REVIEW = '/requests/{request_id}/review'
    REQUESTS_BY_REQUEST_ID_CANCEL = '/requests/{request_id}/cancel'
    BALANCES = '/balances'
    ADMIN_SUMMARY = '/admin-summary'
    CARRY_FORWARD = '/carry-forward'
    BALANCES_ME = '/balances/me'
    IMPACT = '/impact'


class OfferManagementRoutes:
    ROOT = ''
    LOOKUP = '/lookup'
    DUPLICATE_CHECK = '/duplicate-check'
    SUMMARY = '/summary'
    LOOKUPS = '/lookups'
    EXPORT = '/export'
    IMPORT_EXCEL = '/import-excel'
    BY_ENTRY_ID = '/{entry_id}'
    BULK_DELETE = '/bulk-delete'
    BY_ENTRY_ID_HISTORY = '/{entry_id}/history'


class PmsRoutes:
    CONFIG = '/config'
    CONFIG_BY_CONFIG_ID = '/config/{config_id}'
    MONTHLY_AVAILABLE_PERIODS = '/monthly/available-periods'
    MONTHLY = '/monthly'
    MONTHLY_TARGET_ACHIEVEMENT = '/monthly/target-achievement'
    MONTHLY_EXPORT = '/monthly/export'
    MONTHLY_BY_USER_ID = '/monthly/{user_id}'
    MONTHLY_REFRESH = '/monthly/refresh'
    HISTORY = '/history'
    EMPLOYEE_OF_MONTH = '/employee-of-month'
    EMPLOYEE_OF_MONTH_STATS = '/employee-of-month/stats'
    EMPLOYEE_OF_MONTH_RESOLVE = '/employee-of-month/resolve'


class SearchSkuRoutes:
    SEARCH_SKU = '/search-sku'


class SoldPostingRoutes:
    ORDERS = '/orders'
    ORDERS_BY_ORDER_ID = '/orders/{order_id}'
    LINE_ITEMS_BY_LINE_ITEM_RECORD_ID = '/line-items/{line_item_record_id}'
    LINE_ITEMS_BY_LINE_ITEM_RECORD_ID_COPIED = '/line-items/{line_item_record_id}/copied'
    SYNC = '/sync'
    SYNC_STATUS = '/sync-status'
    FILTER_OPTIONS = '/filter-options'


class TaskManagementRoutes:
    CATEGORIES = '/categories'
    CATEGORIES_BY_CATEGORY_ID = '/categories/{category_id}'
    SUBTASKS = '/subtasks'
    SUBTASKS_BY_SUBTASK_ID = '/subtasks/{subtask_id}'
    SUB_SUBTASKS = '/sub-subtasks'
    SUB_SUBTASKS_BY_SUB_SUBTASK_ID = '/sub-subtasks/{sub_subtask_id}'
    ASSIGNMENTS = '/assignments'
    ASSIGNMENTS_BY_ASSIGNMENT_ID = '/assignments/{assignment_id}'
    TASK_ASSIGNMENTS = '/task-assignments'


class EbayTradingCalls:
    GET_BEST_OFFERS = 'GetBestOffers'
    RESPOND_TO_BEST_OFFER = 'RespondToBestOffer'
    GET_MY_MESSAGES = 'GetMyMessages'
    ADD_MEMBER_MESSAGE_TO_PARTNER = 'AddMemberMessageAAQToPartner'
    REPLY_TO_MEMBER_MESSAGE = 'AddMemberMessageRTQ'


class ExternalApi:
    EBAY_ORDER_DETAIL = '{base_url}/{order_id}'
    EBAY_RETURN_PAGE = 'https://www.ebay.com/sh/ord/returns?returnId={return_id}'
    EBAY_CANCELLATION_PAGE = 'https://www.ebay.com/sh/ord/cancellations?cancelId={cancel_id}'
    EBAY_ORDER_PAGE = 'https://www.ebay.com/sh/ord/details?orderId={order_id}'
    DEFAULT_FRONTEND_URL = 'http://localhost:5173 '
    DEFAULT_CORS_ORIGINS = 'http://localhost:5173,http://127.0.0.1:5173,'
    TRANSLATION_DEFAULT_BASE = 'http://127.0.0.1:5001'
    EBAY_SCOPE_BASE = 'https://api.ebay.com/oauth/api_scope'
    EBAY_SCOPE_MESSAGE = 'https://api.ebay.com/oauth/api_scope/commerce.message'
    EBAY_SCOPE_IDENTITY = 'https://api.ebay.com/oauth/api_scope/commerce.identity.readonly'
    EBAY_SCOPE_INVENTORY = 'https://api.ebay.com/oauth/api_scope/sell.inventory'
    EBAY_SCOPE_FULFILLMENT = 'https://api.ebay.com/oauth/api_scope/sell.fulfillment'
    EBAY_PRODUCTION_OAUTH_AUTHORIZE = 'https://auth.ebay.com/oauth2/authorize'
    EBAY_SANDBOX_OAUTH_AUTHORIZE = 'https://auth.sandbox.ebay.com/oauth2/authorize'
    EBAY_PRODUCTION_OAUTH_TOKEN = 'https://api.ebay.com/identity/v1/oauth2/token'
    EBAY_SANDBOX_OAUTH_TOKEN = 'https://api.sandbox.ebay.com/identity/v1/oauth2/token'
    EBAY_PRODUCTION_IDENTITY_USER = 'https://apiz.ebay.com/commerce/identity/v1/user/'
    EBAY_SANDBOX_IDENTITY_USER = 'https://apiz.sandbox.ebay.com/commerce/identity/v1/user/'
    EBAY_PRODUCTION_CONVERSATIONS = 'https://api.ebay.com/commerce/message/v1/conversation'
    EBAY_SANDBOX_CONVERSATIONS = 'https://api.sandbox.ebay.com/commerce/message/v1/conversation'
    EBAY_PRODUCTION_MEDIA_BASE = 'https://apim.ebay.com/commerce/media/v1_beta'
    EBAY_SANDBOX_MEDIA_BASE = 'https://apim.sandbox.ebay.com/commerce/media/v1_beta'
    EBAY_PRODUCTION_ORDERS = 'https://api.ebay.com/sell/fulfillment/v1/order'
    EBAY_SANDBOX_ORDERS = 'https://api.sandbox.ebay.com/sell/fulfillment/v1/order'
    EBAY_PRODUCTION_BASE = 'https://api.ebay.com'
    EBAY_SANDBOX_BASE = 'https://api.sandbox.ebay.com'
    EBAY_NEGOTIATION_BASE = '{host}/sell/negotiation/v1'
    EBAY_PRODUCTION_TRADING = 'https://api.ebay.com/ws/api.dll'
    EBAY_SANDBOX_TRADING = 'https://api.sandbox.ebay.com/ws/api.dll'
    EBAY_SCOPE_NOTIFICATION = 'https://api.ebay.com/oauth/api_scope/commerce.notification.subscription'
    EBAY_SCOPE_OFFER = 'https://api.ebay.com/oauth/api_scope/sell.offer'
    EBAY_CONVERSATION_DETAIL = '{conversations_url}/{conversation_id}?{query}'
    EBAY_CONVERSATION_PATH = '/conversation'
    EBAY_SEND_MESSAGE_PATH = '/send_message'
    EBAY_MEDIA_CREATE_IMAGE = '{base_url}/image/create_image_from_file'
    EBAY_OFFER_DETAIL = 'https://api.ebay.com/sell/negotiation/v1/offer/{offer_id}'
    EBAY_IMAGE_LARGE = 'https://i.ebayimg.com/images/g/{image_id}/s-l1600.jpg'
    EBAY_PRODUCTION_NOTIFICATION_BASE = 'https://api.ebay.com/commerce/notification/v1'
    EBAY_SANDBOX_NOTIFICATION_BASE = 'https://api.sandbox.ebay.com/commerce/notification/v1'
    EBAY_ACTIVITY_CALLBACK = '{base}/api/v1/integrations/ebay/best-offers/activity/{account_id}'
    EBAY_NOTIFICATION_DESTINATION = '/destination'
    EBAY_NOTIFICATION_SUBSCRIPTION = '/subscription'
    EBAY_NOTIFICATION_PUBLIC_KEY = '/public_key/{key_id}'
    EBAY_LISTING_PAGE = 'https://www.ebay.com/itm/{listing_id}'
    ALREZA_BASE = 'https://www.alrezaenterprise.com'
    ALREZA_SEARCH = '{base_url}/search?q={query}'
    BLOGGER_POSTS_FEED = 'https://www.blogger.com/feeds/{blog_id}/posts/default'
    ZOHO_ACCOUNTS_BASE = 'https://accounts.zoho.in'
    ZOHO_OAUTH_TOKEN = '{base_url}/oauth/v2/token'
    ZOHO_INVENTORY_BASE = 'https://www.zohoapis.in/inventory/v1'
    ZOHO_ITEM_IMAGE = 'https://inventory.zoho.in/DocTemplates_ItemImage_Small_{image_document_id}.zbfs?organization_id={organization_id}'
    ZOHO_ITEM_PAGE = 'https://inventory.zoho.in/app/{zoho_organization_id}#/inventory/items/{item_id}'
    ZOHO_APP_PAGE = 'https://inventory.zoho.in/app'
    ZOHO_ITEMS = '{base_url}/items'
    EBAY_SELLER_HUB_ORDER_PAGE = 'https://www.ebay.com/sh/ord/details?orderid={order_id}'
    EBAY_PRODUCTION_BROWSE_ITEM = 'https://api.ebay.com/buy/browse/v1/item/get_item_by_legacy_id'
    EBAY_SANDBOX_BROWSE_ITEM = 'https://api.sandbox.ebay.com/buy/browse/v1/item/get_item_by_legacy_id'
    EBAY_REFERENCE_LISTING_PAGE = 'https://www.ebay.com/itm/{reference_id}'
    EBAY_MESSAGES_PAGE = 'https://my.ebay.com/ws/eBayISAPI.dll?MyMessages&FolderId=0'
    EBAY_ORDER_LISTING_PAGE = 'https://www.ebay.com/itm/{order_id}'
    LOCAL_REPLY_ATTACHMENT = '/api/v1/conversations/attachments/{stored_name}'
    TRANSLATION_PATH = '/translate'
    TRANSLATION_URL = '{normalized_url}/translate'
