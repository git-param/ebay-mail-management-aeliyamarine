from fastapi import APIRouter

from app.api.v1.routes import analytics, audit_logs, auth, categories, conversations, ebay_accounts, message_types, notifications, offers, templates, users
from app.modules.integrations.ebay.routes import ebay_oauth_routes
from app.modules.config_management.router import router as config_router
from app.modules.offer_management.router import router as offer_management_router
from app.modules.pms.router import router as pms_router
from app.modules.search_sku.router import router as search_sku_router
from app.modules.sold_posting.router import router as sold_posting_router
from app.modules.task_management.router import router as task_management_router
<<<<<<< Updated upstream
=======
from app.modules.pms.router import router as pms_router
from app.modules.leave_management.router import router as leave_management_router
>>>>>>> Stashed changes


api_router = APIRouter()
api_router.include_router(auth.router, prefix='/auth', tags=['auth'])
api_router.include_router(users.router, prefix='/users', tags=['users'])
api_router.include_router(ebay_accounts.router, prefix='/ebay-accounts', tags=['ebay-accounts'])
api_router.include_router(categories.router, prefix='/categories', tags=['categories'])
api_router.include_router(conversations.router, prefix='/conversations', tags=['conversations'])
api_router.include_router(offers.router, prefix='/offers', tags=['offers'])
api_router.include_router(notifications.router, prefix='/notifications', tags=['notifications'])
api_router.include_router(audit_logs.router, prefix='/audit-logs', tags=['audit-logs'])
api_router.include_router(analytics.router, prefix='/analytics', tags=['analytics'])
api_router.include_router(templates.router, prefix='/templates', tags=['templates'])
api_router.include_router(message_types.router, prefix='/message-types', tags=['message-types'])
api_router.include_router(message_types.reports_router, prefix='/reports', tags=['message-type-reports'])
api_router.include_router(search_sku_router, tags=['search-sku'])
api_router.include_router(offer_management_router, prefix='/offer-management', tags=['offer-management'])
api_router.include_router(sold_posting_router, prefix='/sold-posting', tags=['sold-posting'])
api_router.include_router(pms_router, prefix='/pms', tags=['pms'])
<<<<<<< Updated upstream
api_router.include_router(task_management_router, prefix='/task-management', tags=['task-management'])
=======
api_router.include_router(leave_management_router, prefix='/leave-management', tags=['leave-management'])
>>>>>>> Stashed changes
api_router.include_router(config_router, prefix='/config', tags=['config'])
api_router.include_router(
    ebay_oauth_routes.router,
    prefix='/integrations/ebay',
    tags=['integrations-ebay'],
)
