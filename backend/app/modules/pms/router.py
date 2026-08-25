from uuid import UUID

from fastapi import APIRouter, Depends, Query, status
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.api.dependencies import get_current_user, require_admin, require_operations_manager_or_admin
from app.db.session import get_db
from app.modules.pms.export import export_monthly_table, export_monthly_tables, fiscal_year_label, month_token
from app.modules.pms.schema import (
    PmsEmployeeOfMonthResolveRequest,
    PmsEmployeeOfMonthResponse,
    PmsEmployeeOfMonthStatsResponse,
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


@router.delete('/config/{config_id}', status_code=status.HTTP_204_NO_CONTENT)
def delete_config(config_id: UUID, db: Session = Depends(get_db), current_user=Depends(require_admin)):
    service = PmsService(db)
    service.delete_config(current_user, config_id)


# ----------------------------------------------------------------------
# Monthly PMS
# ----------------------------------------------------------------------

@router.get('/monthly/available-periods')
def get_monthly_available_periods(
    search: str | None = Query(default=None),
    db: Session = Depends(get_db),
    current_user=Depends(require_operations_manager_or_admin),
):
    service = PmsService(db)
    return {'items': service.get_available_monthly_periods(current_user, search=search)}


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


@router.get('/monthly/export')
def export_monthly_table_excel(
    year: int | None = Query(default=None),
    month: int | None = Query(default=None, ge=1, le=12),
    from_year: int | None = Query(default=None),
    from_month: int | None = Query(default=None, ge=1, le=12),
    to_year: int | None = Query(default=None),
    to_month: int | None = Query(default=None, ge=1, le=12),
    search: str | None = Query(default=None),
    target_achievement_percent: float | None = Query(default=None, ge=0, le=100),
    db: Session = Depends(get_db),
    current_user=Depends(require_operations_manager_or_admin),
):
    service = PmsService(db)
    if from_year and from_month and to_year and to_month:
        start_index = from_year * 12 + from_month
        end_index = to_year * 12 + to_month
        if start_index > end_index:
            from fastapi import HTTPException
            raise HTTPException(status_code=422, detail='From month must be before or equal to To month')
        if end_index - start_index > 59:
            from fastapi import HTTPException
            raise HTTPException(status_code=422, detail='PMS export range cannot exceed 60 months')

        tables = []
        current_year = from_year
        current_month = from_month
        while current_year * 12 + current_month <= end_index:
            tables.append(service.get_monthly_table(current_user, current_year, current_month, search))
            current_month += 1
            if current_month > 12:
                current_month = 1
                current_year += 1
        output = export_monthly_tables(tables)
        filename = f'PMS_Monthly_Data_{month_token(from_year, from_month)}_to_{month_token(to_year, to_month)}.xlsx'.replace("'", '')
    else:
        if year is None or month is None:
            from fastapi import HTTPException
            raise HTTPException(status_code=422, detail='Either year/month or from/to month range is required')
        table = service.get_monthly_table(current_user, year, month, search)
        output = export_monthly_table(table, target_achievement_percent=target_achievement_percent)
        filename = f'PMS_Monthly_Data_{fiscal_year_label(year, month)}.xlsx'
    return StreamingResponse(
        output,
        media_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        headers={'Content-Disposition': f'attachment; filename="{filename}"'},
    )


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


@router.get('/employee-of-month/stats', response_model=PmsEmployeeOfMonthStatsResponse)
def get_employee_of_month_stats(db: Session = Depends(get_db), current_user=Depends(require_operations_manager_or_admin)):
    service = PmsService(db)
    return service.get_employee_of_month_stats(current_user)


@router.post('/employee-of-month/resolve', response_model=PmsEmployeeOfMonthResponse)
def resolve_employee_of_month(payload: PmsEmployeeOfMonthResolveRequest, db: Session = Depends(get_db), current_user=Depends(require_admin)):
    service = PmsService(db)
    return service.resolve_employee_of_month(current_user, payload)
