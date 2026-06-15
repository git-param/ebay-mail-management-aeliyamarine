from fastapi import APIRouter

from app.api.v1.routes import auth, ebay_accounts, users


api_router = APIRouter()
api_router.include_router(auth.router, prefix='/auth', tags=['auth'])
api_router.include_router(users.router, prefix='/users', tags=['users'])
api_router.include_router(ebay_accounts.router, prefix='/ebay-accounts', tags=['ebay-accounts'])
