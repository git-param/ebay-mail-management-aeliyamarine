from importlib import import_module

from fastapi import APIRouter

from app.constants.api import ApiPrefixes
from app.api.v1.routes import analytics, audit_logs, auth, categories, conversations, ebay_accounts, message_types, notifications, offers, templates, users
from app.modules.integrations.ebay.routes import ebay_oauth_routes
from app.modules.config_management.router import router as config_router
from app.modules.offer_management.router import router as offer_management_router
from app.modules.daily_task_entry.router import router as daily_entry_router
from app.modules.search_sku.router import router as search_sku_router
from app.modules.sold_posting.router import router as sold_posting_router
from app.modules.task_management.router import router as task_management_router
from app.modules.pms.router import router as pms_router
from app.modules.leave_management.router import router as leave_management_router
from app.modules.pms.router import router as pms_router
break_management_router = import_module('app.modules.break-maagement.router').router


api_router = APIRouter()
api_router.include_router(auth.router, prefix=ApiPrefixes.AUTH, tags=['auth'])
api_router.include_router(users.router, prefix=ApiPrefixes.USERS, tags=['users'])
api_router.include_router(ebay_accounts.router, prefix=ApiPrefixes.EBAY_ACCOUNTS, tags=['ebay-accounts'])
api_router.include_router(categories.router, prefix=ApiPrefixes.CATEGORIES, tags=['categories'])
api_router.include_router(conversations.router, prefix=ApiPrefixes.CONVERSATIONS, tags=['conversations'])
api_router.include_router(offers.router, prefix=ApiPrefixes.OFFERS, tags=['offers'])
api_router.include_router(notifications.router, prefix=ApiPrefixes.NOTIFICATIONS, tags=['notifications'])
api_router.include_router(audit_logs.router, prefix=ApiPrefixes.AUDIT_LOGS, tags=['audit-logs'])
api_router.include_router(analytics.router, prefix=ApiPrefixes.ANALYTICS, tags=['analytics'])
api_router.include_router(templates.router, prefix=ApiPrefixes.TEMPLATES, tags=['templates'])
api_router.include_router(message_types.router, prefix=ApiPrefixes.MESSAGE_TYPES, tags=['message-types'])
api_router.include_router(message_types.reports_router, prefix=ApiPrefixes.REPORTS, tags=['message-type-reports'])
api_router.include_router(search_sku_router, tags=['search-sku'])
api_router.include_router(offer_management_router, prefix=ApiPrefixes.OFFER_MANAGEMENT, tags=['offer-management'])
api_router.include_router(sold_posting_router, prefix=ApiPrefixes.SOLD_POSTING, tags=['sold-posting'])
api_router.include_router(pms_router, prefix=ApiPrefixes.PMS, tags=['pms'])
api_router.include_router(task_management_router, prefix=ApiPrefixes.TASK_MANAGEMENT, tags=['task-management'])
api_router.include_router(leave_management_router, prefix=ApiPrefixes.LEAVE_MANAGEMENT, tags=['leave-management'])
api_router.include_router(break_management_router, prefix=ApiPrefixes.BREAK_MANAGEMENT, tags=['break-management'])
api_router.include_router(daily_entry_router, prefix=ApiPrefixes.DAILY_ENTRY, tags=['daily-entry'])
api_router.include_router(task_management_router, prefix=ApiPrefixes.TASK_MANAGEMENT, tags=['task-management'])
api_router.include_router(pms_router, prefix=ApiPrefixes.PMS, tags=['pms'])
api_router.include_router(config_router, prefix=ApiPrefixes.CONFIG, tags=['config'])
api_router.include_router(ebay_oauth_routes.router,prefix=ApiPrefixes.INTEGRATIONS_EBAY,tags=['integrations-ebay'])

from app.modules.integrations.ebay.routes.ebay_best_offer_routes import router as best_offer_router
api_router.include_router(best_offer_router, prefix=ApiPrefixes.INTEGRATIONS_EBAY_BEST_OFFERS, tags=['eBay Best Offers'])
