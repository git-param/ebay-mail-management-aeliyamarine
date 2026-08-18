from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.dependencies import get_current_user, require_admin, require_operations_manager_or_admin
from app.db.session import get_db
from app.modules.pms.schema import (
    PmsEmployeeOfMonthResolveRequest,
    PmsEmployeeOfMonthResponse,
    PmsHistoryResponse,
    PmsMetricConfigCreate,
    PmsMetricConfigListResponse,
    PmsMetricConfigResponse,
    PmsMetricConfigUpdate,
    PmsMonthlyRecordResponse,
    PmsMonthlyRefreshRequest,
    PmsMonthlySaveRequest,
    PmsMonthlyTableResponse,
)
from app.modules.pms.service import PmsService


router = APIRouter()


# ----------------------------------------------------------------------
# Configuration — Admin manages, Admin/Ops Manager can read
# ----------------------------------------------------------------------

@router.get('/config', response_model=PmsMetricConfigListResponse)
def list_config(db: Session = Depends(get_db), current_user=Depends(require_operations_manager_or_admin)):
    service = PmsService(db)
    items, total_active_weight = service.list_config()
    return {'items': items, 'total_active_weight': total_active_weight}


@router.post('/config', response_model=PmsMetricConfigResponse)
def create_config(payload: PmsMetricConfigCreate, db: Session = Depends(get_db), current_user=Depends(require_admin)):
    service = PmsService(db)
    return service.create_config(current_user, payload)


@router.put('/config/{config_id}', response_model=PmsMetricConfigResponse)
def update_config(config_id: UUID, payload: PmsMetricConfigUpdate, db: Session = Depends(get_db), current_user=Depends(require_admin)):
    service = PmsService(db)
    return service.update_config(current_user, config_id, payload)


# ----------------------------------------------------------------------
# Monthly PMS
# ----------------------------------------------------------------------

@router.get('/monthly', response_model=PmsMonthlyTableResponse)
def get_monthly_table(
    year: int = Query(...),
    month: int = Query(..., ge=1, le=12),
    search: str | None = Query(default=None),
    db: Session = Depends(get_db),
    current_user=Depends(require_operations_manager_or_admin),
):
    service = PmsService(db)
    return service.get_monthly_table(current_user, year, month, search)


@router.get('/monthly/{user_id}', response_model=PmsMonthlyRecordResponse)
def get_monthly_record(
    user_id: UUID,
    year: int = Query(...),
    month: int = Query(..., ge=1, le=12),
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    # Authorization (self-only for Agents) is enforced inside the service so
    # it lives alongside the rest of PMS's RBAC rules.
    service = PmsService(db)
    return service.get_monthly_record(current_user, user_id, year, month)


@router.post('/monthly/refresh', response_model=PmsMonthlyRecordResponse)
def refresh_auto_values(payload: PmsMonthlyRefreshRequest, db: Session = Depends(get_db), current_user=Depends(require_admin)):
    service = PmsService(db)
    return service.refresh_auto_values(current_user, payload)


@router.post('/monthly', response_model=PmsMonthlyRecordResponse)
def save_monthly(payload: PmsMonthlySaveRequest, db: Session = Depends(get_db), current_user=Depends(require_admin)):
    service = PmsService(db)
    return service.save_monthly(current_user, payload)


# ----------------------------------------------------------------------
# History
# ----------------------------------------------------------------------

@router.get('/history', response_model=PmsHistoryResponse)
def get_history(
    year: int | None = Query(default=None),
    month: int | None = Query(default=None, ge=1, le=12),
    user_id: UUID | None = Query(default=None),
    search: str | None = Query(default=None),
    status: str | None = Query(default=None),
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    # Agent scoping (self-only) is enforced inside the service.
    service = PmsService(db)
    return service.get_history(current_user, year=year, month=month, user_id=user_id, search=search, status_filter=status)


# ----------------------------------------------------------------------
# Employee of the Month
# ----------------------------------------------------------------------

@router.get('/employee-of-month', response_model=PmsEmployeeOfMonthResponse)
def get_employee_of_month(
    year: int = Query(...),
    month: int = Query(..., ge=1, le=12),
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    service = PmsService(db)
    return service.get_employee_of_month(current_user, year, month)


@router.post('/employee-of-month/resolve', response_model=PmsEmployeeOfMonthResponse)
def resolve_employee_of_month(payload: PmsEmployeeOfMonthResolveRequest, db: Session = Depends(get_db), current_user=Depends(require_admin)):
    service = PmsService(db)
    return service.resolve_employee_of_month(current_user, payload)