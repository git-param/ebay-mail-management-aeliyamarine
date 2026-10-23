from datetime import date
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.dependencies import get_current_user
from app.db.session import get_db
from app.modules.daily_reports.schemas import DailyReportListResponse, DailyReportResponse, DailyReportUser, ReportCopyRequest, ReportTasksUpdate
from app.modules.daily_reports.service import DailyReportService


router = APIRouter()


@router.get('/users', response_model=list[DailyReportUser])
def users(db: Session = Depends(get_db), current_user=Depends(get_current_user)):
    return DailyReportService(db).report_users(current_user)


@router.get('/today', response_model=DailyReportResponse)
def today(db: Session = Depends(get_db), current_user=Depends(get_current_user)):
    return DailyReportService(db).today(current_user)


@router.put('/today/tasks', response_model=DailyReportResponse)
def save_tasks(payload: ReportTasksUpdate, db: Session = Depends(get_db), current_user=Depends(get_current_user)):
    return DailyReportService(db).save_today(current_user, payload.report_date, payload.tasks)


@router.post('/today/copy', response_model=DailyReportResponse)
def copy_today(payload: ReportCopyRequest, db: Session = Depends(get_db), current_user=Depends(get_current_user)):
    return DailyReportService(db).save_today(current_user, payload.report_date, copied=True)


@router.get('', response_model=DailyReportListResponse)
def list_reports(date_from: date | None = None, date_to: date | None = None, user_id: UUID | None = None,
                 limit: int = Query(50, ge=1, le=200), offset: int = Query(0, ge=0),
                 db: Session = Depends(get_db), current_user=Depends(get_current_user)):
    return DailyReportService(db).list_reports(current_user, date_from=date_from, date_to=date_to,
                                                user_id=user_id, limit=limit, offset=offset)
