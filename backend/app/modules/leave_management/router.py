from uuid import UUID

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from app.constants.api import LeaveManagementRoutes
from app.api.dependencies import get_current_user, require_admin
from app.db.session import get_db
from app.modules.leave_management.schemas import (
    LeaveBalanceResponse,
    LeaveCarryForwardResponse,
    LeaveCarryForwardUpdate,
    LeaveImpactResponse,
    LeaveAdminSummaryRow,
    LeaveAdminSummaryUpdate,
    LeavePolicyResponse,
    LeavePolicyUpdate,
    LeaveRequestCreate,
    LeaveRequestListResponse,
    LeaveRequestResponse,
    LeaveReviewRequest,
)
from app.modules.leave_management.service import LeaveManagementService


router = APIRouter()


@router.get(LeaveManagementRoutes.POLICY, response_model=LeavePolicyResponse)
def get_policy(db: Session = Depends(get_db), current_user=Depends(get_current_user)):
    return LeaveManagementService(db).get_policy()


@router.put(LeaveManagementRoutes.POLICY, response_model=LeavePolicyResponse)
def update_policy(payload: LeavePolicyUpdate, db: Session = Depends(get_db), current_user=Depends(require_admin)):
    return LeaveManagementService(db).update_policy(current_user, payload)


@router.post(LeaveManagementRoutes.REQUESTS, response_model=LeaveRequestResponse, status_code=status.HTTP_201_CREATED)
def create_request(payload: LeaveRequestCreate, db: Session = Depends(get_db), current_user=Depends(get_current_user)):
    service = LeaveManagementService(db)
    return service.serialize_request(service.create_request(current_user, payload))


@router.get(LeaveManagementRoutes.REQUESTS, response_model=LeaveRequestListResponse)
def list_requests(
    user_id: UUID | None = Query(default=None),
    leave_type: str | None = Query(default=None),
    status_filter: str | None = Query(default=None, alias='status'),
    year: int | None = Query(default=None),
    month: int | None = Query(default=None, ge=1, le=12),
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    service = LeaveManagementService(db)
    items = service.list_requests(current_user, user_id=user_id, leave_type=leave_type, status_filter=status_filter, year=year, month=month)
    return {'items': [service.serialize_request(item) for item in items], 'total': len(items)}


@router.post(LeaveManagementRoutes.REQUESTS_BY_REQUEST_ID_REVIEW, response_model=LeaveRequestResponse)
def review_request(request_id: UUID, payload: LeaveReviewRequest, db: Session = Depends(get_db), current_user=Depends(require_admin)):
    service = LeaveManagementService(db)
    return service.serialize_request(service.review_request(current_user, request_id, payload))


@router.post(LeaveManagementRoutes.REQUESTS_BY_REQUEST_ID_CANCEL, response_model=LeaveRequestResponse)
def cancel_request(request_id: UUID, db: Session = Depends(get_db), current_user=Depends(get_current_user)):
    service = LeaveManagementService(db)
    return service.serialize_request(service.cancel_request(current_user, request_id))


@router.get(LeaveManagementRoutes.BALANCES, response_model=list[LeaveBalanceResponse])
def list_balances(
    year: int = Query(...),
    month: int = Query(..., ge=1, le=12),
    user_id: UUID | None = Query(default=None),
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    return LeaveManagementService(db).list_balances(current_user, year, month, user_id)


@router.get(LeaveManagementRoutes.ADMIN_SUMMARY, response_model=list[LeaveAdminSummaryRow])
def admin_summary(
    year: int = Query(...),
    month: int = Query(..., ge=1, le=12),
    db: Session = Depends(get_db),
    current_user=Depends(require_admin),
):
    return LeaveManagementService(db).list_admin_summary(current_user, year, month)


@router.put(LeaveManagementRoutes.ADMIN_SUMMARY, response_model=list[LeaveAdminSummaryRow])
def update_admin_summary(payload: LeaveAdminSummaryUpdate, db: Session = Depends(get_db), current_user=Depends(require_admin)):
    return LeaveManagementService(db).update_admin_summary(current_user, payload)


@router.get(LeaveManagementRoutes.CARRY_FORWARD, response_model=LeaveCarryForwardResponse)
def get_carry_forward(
    user_id: UUID,
    year: int = Query(...),
    month: int = Query(..., ge=1, le=12),
    db: Session = Depends(get_db),
    current_user=Depends(require_admin),
):
    return LeaveManagementService(db).get_carry_forward(current_user, user_id, year, month)


@router.put(LeaveManagementRoutes.CARRY_FORWARD, response_model=LeaveCarryForwardResponse)
def update_carry_forward(payload: LeaveCarryForwardUpdate, db: Session = Depends(get_db), current_user=Depends(require_admin)):
    return LeaveManagementService(db).update_carry_forward(current_user, payload)


@router.get(LeaveManagementRoutes.BALANCES_ME, response_model=LeaveBalanceResponse)
def my_balance(year: int = Query(...), month: int = Query(..., ge=1, le=12), db: Session = Depends(get_db), current_user=Depends(get_current_user)):
    return LeaveManagementService(db).get_balance(current_user, current_user.id, year, month)


@router.get(LeaveManagementRoutes.IMPACT, response_model=LeaveImpactResponse)
def get_impact(
    user_id: UUID,
    year: int = Query(...),
    month: int = Query(..., ge=1, le=12),
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    service = LeaveManagementService(db)
    service._authorize_self_or_admin(current_user, user_id)
    return service.pms_impact_for_user_month(user_id, year, month)
