from uuid import UUID
from datetime import UTC, datetime
from typing import Literal
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy import select, func
from app.constants.api import EbayBestOfferRoutes
from app.api.dependencies import get_current_user, require_operations_manager_or_admin, normalized_role_name
from app.db.session import get_db
from app.models.conversation import SyncLog
from app.models.offer import Offer
from app.repositories.permission_repository import PermissionRepository
from app.modules.integrations.ebay.schemas.best_offer_schemas import BestOfferConfigUpdate, BestOfferSyncRequest, BestOfferActionRequest
from app.modules.integrations.ebay.services.ebay_best_offer_query_service import EbayBestOfferQueryService, negotiation_identity
from app.modules.integrations.ebay.services.ebay_best_offer_action_service import EbayBestOfferActionService
from app.services.ebay_best_offer_job_service import EbayBestOfferJobService, ACCOUNT, BATCH, job_response
from app.services.ebay_best_offer_worker import dispatch

router = APIRouter()


def require_offer_view(user=Depends(get_current_user)):
    if normalized_role_name(user) not in {'ADMIN','OPS_MANAGER','OPERATIONS_MANAGER','AGENT','SUPPORT_AGENT'}:
        raise HTTPException(403, 'Offer Management access required')
    return user


@router.get(EbayBestOfferRoutes.CURRENT)
def current(account_id: UUID | None = None, status: str | None = None,
            lifecycle: Literal['OPEN','AGREED','COMPLETED','CLOSED','UNKNOWN'] | None = None,
            view: Literal['current', 'history', 'all', 'done'] = 'current',
            search: str | None = Query(default=None, max_length=255), buyer: str | None = None, item_id: str | None = None,
            checked_after: datetime | None = None,
            role: Literal['Buyer','Seller','Unknown'] | None = None,
            sort: Literal['expiring','newest','amount','listing_price']='expiring',
            page: int = Query(1, ge=1), page_size: int = Query(25, ge=1, le=100),
            db=Depends(get_db), user=Depends(require_offer_view)):
    allowed = bool(user.role_id and PermissionRepository(db).role_has_permission(user.role_id, 'offer.respond'))
    return EbayBestOfferQueryService(db).list(account_id=account_id, status=status, lifecycle=lifecycle, view=view, search=search, buyer=buyer,
        item_id=item_id, role=role, checked_after=checked_after, sort=sort, page=page, page_size=page_size, can_respond=allowed)


@router.post(EbayBestOfferRoutes.BY_OFFER_ID_DONE)
def mark_done(offer_id: UUID, db=Depends(get_db), user=Depends(require_offer_view)):
    offer = db.get(Offer, offer_id)
    if not offer or offer.provider != 'EBAY':
        raise HTTPException(404, 'Offer not found')
    key = negotiation_identity(offer)
    if len(key) == 1:
        group = [offer]
    else:
        group = db.scalars(select(Offer).where(Offer.provider == 'EBAY',
            Offer.account_id == key[0], Offer.listing_id == key[1],
            func.lower(func.trim(Offer.buyer_username)) == key[2],
            Offer.record_source != 'DERIVED')).all()
    if any(row.done_at is None for row in group):
        done_at = datetime.now(UTC)
        for row in group:
            row.done_at = done_at
        from app.services.audit_service import AuditService
        AuditService(db).log(action='EBAY_BEST_OFFER_MARKED_DONE', user_id=user.id,
            entity_type='OFFER', entity_id=offer.id, category='OFFER_MANAGEMENT')
        db.commit()
    return {'id': offer.id, 'done_at': offer.done_at}


@router.get(EbayBestOfferRoutes.ACCOUNTS)
def accounts(db=Depends(get_db), user=Depends(require_offer_view)):
    from app.models.ebay_account import EbayAccount
    return {'items': [{'id': a.id, 'name': a.account_name} for a in db.scalars(select(EbayAccount).order_by(EbayAccount.account_name))]}


@router.get(EbayBestOfferRoutes.CONFIG)
def config(db=Depends(get_db), user=Depends(require_operations_manager_or_admin)):
    return EbayBestOfferJobService(db).config()


@router.patch(EbayBestOfferRoutes.CONFIG)
def update_config(payload: BestOfferConfigUpdate, db=Depends(get_db), user=Depends(require_operations_manager_or_admin)):
    return EbayBestOfferJobService(db).update_config(payload, user)


@router.post(EbayBestOfferRoutes.SYNC, status_code=202)
def sync(payload: BestOfferSyncRequest, db=Depends(get_db), user=Depends(require_operations_manager_or_admin)):
    return dispatch(EbayBestOfferJobService(db).reserve(payload.account_ids, user=user, include_history=payload.include_history))


@router.get(EbayBestOfferRoutes.JOBS_BY_JOB_ID)
def job(job_id: UUID, db=Depends(get_db), user=Depends(require_operations_manager_or_admin)):
    record = db.get(SyncLog, job_id)
    if not record or record.sync_type not in {ACCOUNT, BATCH}:
        raise HTTPException(404, 'Best Offer job not found')
    result = job_response(record)
    if record.sync_type == BATCH:
        result['jobs'] = [job_response(j) for j in db.scalars(select(SyncLog).where(SyncLog.id.in_(
            (record.sync_metadata or {}).get('jobs', []))))]
    return result


@router.post(EbayBestOfferRoutes.BY_OFFER_ID_RESPOND)
def respond(offer_id: UUID, payload: BestOfferActionRequest, db=Depends(get_db), user=Depends(require_offer_view)):
    # Synchronous route runs in FastAPI's thread pool, never the event loop.
    return EbayBestOfferActionService(db).respond(offer_id, payload, user)


@router.post(EbayBestOfferRoutes.JOBS_BY_JOB_ID_CANCEL)
def cancel_job(job_id: UUID, db=Depends(get_db), user=Depends(require_operations_manager_or_admin)):
    return EbayBestOfferJobService(db).cancel(job_id, user)


@router.get(EbayBestOfferRoutes.ACTIVITY_BY_ACCOUNT_ID)
def activity_challenge(account_id: UUID, challenge_code: str = Query(min_length=1, max_length=512), db=Depends(get_db)):
    from app.modules.integrations.ebay.services.ebay_offer_activity_service import EbayOfferActivityService
    return EbayOfferActivityService(db).challenge(account_id, challenge_code)


@router.post(EbayBestOfferRoutes.ACTIVITY_BY_ACCOUNT_ID)
async def activity_receive(account_id: UUID, request: Request, db=Depends(get_db)):
    from starlette.concurrency import run_in_threadpool
    from app.modules.integrations.ebay.services.ebay_offer_activity_service import EbayOfferActivityService
    body = bytearray()
    async for chunk in request.stream():
        body.extend(chunk)
        if len(body) > 262144:
            raise HTTPException(413, 'Notification is too large')
    return await run_in_threadpool(EbayOfferActivityService(db).receive, account_id, bytes(body), request.headers.get('x-ebay-signature'))


@router.post(EbayBestOfferRoutes.ACTIVITY_BY_ACCOUNT_ID_AUTHORIZE)
def authorize_activity(account_id: UUID, db=Depends(get_db), user=Depends(require_operations_manager_or_admin)):
    if normalized_role_name(user) != 'ADMIN':
        raise HTTPException(403, 'Only admins can reconnect eBay accounts')
    from app.modules.integrations.ebay.oauth.oauth_service import EbayOAuthService
    from app.services.audit_service import AuditService
    url, _ = EbayOAuthService(db).create_authorization_url(account_id, offer_activity=True)
    AuditService(db).log(action='EBAY_OFFER_ACTIVITY_CONSENT_REQUESTED', user_id=user.id,
        entity_type='EBAY_ACCOUNT', entity_id=account_id, category='OFFER_MANAGEMENT')
    db.commit()
    return {'authorization_url': url}


@router.post(EbayBestOfferRoutes.ACTIVITY_BY_ACCOUNT_ID_SETUP)
def setup_activity(account_id: UUID, db=Depends(get_db), user=Depends(require_operations_manager_or_admin)):
    from app.modules.integrations.ebay.services.ebay_offer_activity_service import EbayOfferActivityService
    from app.services.audit_service import AuditService
    result = EbayOfferActivityService(db).setup(account_id)
    AuditService(db).log(action='EBAY_OFFER_ACTIVITY_ENABLED', user_id=user.id,
        entity_type='EBAY_ACCOUNT', entity_id=account_id, category='OFFER_MANAGEMENT')
    db.commit()
    return result
