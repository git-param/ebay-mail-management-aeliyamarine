import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.v1.router import api_router
from app.core.config import get_settings
from app.services.ebay_auto_sync_service import ebay_auto_sync_loop
from app.services.notification_cleanup import notification_cleanup_loop


@asynccontextmanager
async def lifespan(app: FastAPI):
    cleanup_task = asyncio.create_task(notification_cleanup_loop())
    ebay_auto_sync_task = asyncio.create_task(ebay_auto_sync_loop())
    try:
        yield
    finally:
        for task in (cleanup_task, ebay_auto_sync_task):
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass


def create_app() -> FastAPI:
    settings = get_settings()

    app = FastAPI(
        title=settings.project_name,
        version=settings.api_version,
        lifespan=lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=['*'],
        allow_headers=['*'],
    )

    app.include_router(api_router, prefix='/api/v1')

    @app.get('/health', tags=['health'])
    def health_check() -> dict[str, str]:
        return {'status': 'ok'}

    return app


app = create_app()
