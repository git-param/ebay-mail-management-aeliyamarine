from datetime import date
from uuid import UUID

from fastapi import APIRouter, Depends, Query, status
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.api.dependencies import get_current_user, require_operations_manager_or_admin
from app.db.session import get_db
from .schemas import (
    BreakHistoryResponse,
    BreakOverviewResponse,
    BreakSessionResponse,
    BreakStartRequest,
    BreakStatusResponse,
)
from .service import BreakManagementService
from .export import export_break_workbook


router = APIRouter()


@router.get('/status', response_model=BreakStatusResponse)
def get_status(db: Session = Depends(get_db), current_user=Depends(get_current_user)):
    return BreakManagementService(db).status(current_user)


@router.post('/start', response_model=BreakSessionResponse, status_code=status.HTTP_201_CREATED)
def start_break(payload: BreakStartRequest, db: Session = Depends(get_db), current_user=Depends(get_current_user)):
    return BreakManagementService(db).start_break(current_user, payload)


@router.post('/end', response_model=BreakSessionResponse)
def end_break(db: Session = Depends(get_db), current_user=Depends(get_current_user)):
    return BreakManagementService(db).end_break(current_user)


@router.get('/history', response_model=BreakHistoryResponse)
def get_history(
    user_id: UUID | None = Query(default=None),
    date_from: date | None = Query(default=None),
    date_to: date | None = Query(default=None),
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    return BreakManagementService(db).history(current_user, user_id, date_from, date_to)


@router.get('/overview', response_model=BreakOverviewResponse)
def get_overview(
    selected_date: date | None = Query(default=None, alias='date'),
    db: Session = Depends(get_db),
    current_user=Depends(require_operations_manager_or_admin),
):
    return BreakManagementService(db).overview(selected_date)


@router.get('/employees')
def list_export_employees(
    db: Session = Depends(get_db),
    current_user=Depends(require_operations_manager_or_admin),
):
    users, _ = BreakManagementService(db).export_data(None, date.today(), date.today())
    return {'items': [{'id': user.id, 'name': user.full_name, 'role': user.role.name if user.role else ''} for user in users]}


@router.get('/export')
def export_breaks(
    date_from: date = Query(...),
    date_to: date = Query(...),
    user_ids: list[UUID] | None = Query(default=None),
    db: Session = Depends(get_db),
    current_user=Depends(require_operations_manager_or_admin),
):
    users, sessions = BreakManagementService(db).export_data(user_ids, date_from, date_to)
    output = export_break_workbook(users, sessions, date_from, date_to)
    filename = f'break_report_{date_from}_{date_to}.xlsx'
    return StreamingResponse(
        output,
        media_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        headers={'Content-Disposition': f'attachment; filename="{filename}"'},
    )
