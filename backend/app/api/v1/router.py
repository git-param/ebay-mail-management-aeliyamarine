from fastapi import APIRouter

from app.api.v1.routes import analytics, audit_logs, auth, categories, conversations, ebay_accounts, message_types, notifications, templates, users
from app.modules.integrations.ebay.routes import ebay_oauth_routes


api_router = APIRouter()
api_router.include_router(auth.router, prefix='/auth', tags=['auth'])
api_router.include_router(users.router, prefix='/users', tags=['users'])
api_router.include_router(ebay_accounts.router, prefix='/ebay-accounts', tags=['ebay-accounts'])
api_router.include_router(categories.router, prefix='/categories', tags=['categories'])
api_router.include_router(conversations.router, prefix='/conversations', tags=['conversations'])
api_router.include_router(notifications.router, prefix='/notifications', tags=['notifications'])
api_router.include_router(audit_logs.router, prefix='/audit-logs', tags=['audit-logs'])
api_router.include_router(analytics.router, prefix='/analytics', tags=['analytics'])
api_router.include_router(templates.router, prefix='/templates', tags=['templates'])
api_router.include_router(message_types.router, prefix='/message-types', tags=['message-types'])
api_router.include_router(message_types.reports_router, prefix='/reports', tags=['message-type-reports'])
api_router.include_router(
    ebay_oauth_routes.router,
    prefix='/integrations/ebay',
    tags=['integrations-ebay'],
)
