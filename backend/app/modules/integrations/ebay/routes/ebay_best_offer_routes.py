from uuid import UUID
from typing import Literal
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from app.api.dependencies import get_current_user, require_operations_manager_or_admin, normalized_role_name
from app.db.session import get_db
from app.models.conversation import SyncLog
from app.repositories.permission_repository import PermissionRepository
from app.modules.integrations.ebay.schemas.best_offer_schemas import BestOfferConfigUpdate, BestOfferSyncRequest, BestOfferActionRequest
from app.modules.integrations.ebay.services.ebay_best_offer_query_service import EbayBestOfferQueryService
from app.modules.integrations.ebay.services.ebay_best_offer_action_service import EbayBestOfferActionService
from app.services.ebay_best_offer_job_service import EbayBestOfferJobService, ACCOUNT, BATCH, job_response
from app.services.ebay_best_offer_worker import dispatch

router = APIRouter()


def require_offer_view(user=Depends(get_current_user)):
    if normalized_role_name(user) not in {'ADMIN','OPS_MANAGER','OPERATIONS_MANAGER','AGENT','SUPPORT_AGENT'}:
        raise HTTPException(403, 'Offer Management access required')
    return user


@router.get('/current')
def current(account_id: UUID | None = None, status: str | None = None,
            search: str | None = Query(default=None, max_length=255), buyer: str | None = None, item_id: str | None = None,
            sort: Literal['expiring','newest','amount','listing_price']='expiring',
            page: int = Query(1, ge=1), page_size: int = Query(25, ge=1, le=100),
            db=Depends(get_db), user=Depends(require_offer_view)):
    allowed = bool(user.role_id and PermissionRepository(db).role_has_permission(user.role_id, 'offer.respond'))
    return EbayBestOfferQueryService(db).list(account_id=account_id, status=status, search=search, buyer=buyer,
        item_id=item_id, sort=sort, page=page, page_size=page_size, can_respond=allowed)


@router.get('/accounts')
def accounts(db=Depends(get_db), user=Depends(require_offer_view)):
    from app.models.ebay_account import EbayAccount
    return {'items': [{'id': a.id, 'name': a.account_name} for a in db.scalars(select(EbayAccount).order_by(EbayAccount.account_name))]}


@router.get('/config')
def config(db=Depends(get_db), user=Depends(require_operations_manager_or_admin)):
    return EbayBestOfferJobService(db).config()


@router.patch('/config')
def update_config(payload: BestOfferConfigUpdate, db=Depends(get_db), user=Depends(require_operations_manager_or_admin)):
    return EbayBestOfferJobService(db).update_config(payload, user)


@router.post('/sync', status_code=202)
def sync(payload: BestOfferSyncRequest, db=Depends(get_db), user=Depends(require_operations_manager_or_admin)):
    return dispatch(EbayBestOfferJobService(db).reserve(payload.account_ids, user=user))


@router.get('/jobs/{job_id}')
def job(job_id: UUID, db=Depends(get_db), user=Depends(require_operations_manager_or_admin)):
    record = db.get(SyncLog, job_id)
    if not record or record.sync_type not in {ACCOUNT, BATCH}:
        raise HTTPException(404, 'Best Offer job not found')
    result = job_response(record)
    if record.sync_type == BATCH:
        result['jobs'] = [job_response(j) for j in db.scalars(select(SyncLog).where(SyncLog.id.in_(
            (record.sync_metadata or {}).get('jobs', []))))]
    return result


@router.post('/{offer_id}/respond')
def respond(offer_id: UUID, payload: BestOfferActionRequest, db=Depends(get_db), user=Depends(require_offer_view)):
    # Synchronous route runs in FastAPI's thread pool, never the event loop.
    return EbayBestOfferActionService(db).respond(offer_id, payload, user)
