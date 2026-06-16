from fastapi import APIRouter

from app.api.v1.routes import auth, categories, conversations, ebay_accounts, users
from app.modules.integrations.ebay.routes import ebay_oauth_routes


api_router = APIRouter()
api_router.include_router(auth.router, prefix='/auth', tags=['auth'])
api_router.include_router(users.router, prefix='/users', tags=['users'])
api_router.include_router(ebay_accounts.router, prefix='/ebay-accounts', tags=['ebay-accounts'])
api_router.include_router(categories.router, prefix='/categories', tags=['categories'])
api_router.include_router(conversations.router, prefix='/conversations', tags=['conversations'])
api_router.include_router(
    ebay_oauth_routes.router,
    prefix='/integrations/ebay',
    tags=['integrations-ebay'],
)
