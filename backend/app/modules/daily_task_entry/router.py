from datetime import date
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.dependencies import get_current_user
from app.db.session import get_db
from app.modules.daily_task_entry.schemas import (
    DailyEntryCreate,
    DailyEntryDraftResponse,
    DailyEntryLoadResponse,
    DailyEntryResponse,
    DailyEntrySLAReviewResponse,
    DailyEntryUploadResponse,
    DailyEntryListResponse,
    DailyEntryLoadResponse,
    DailyEntrySLAReviewResponse,
    DailyEntryUploadRequest,
    DailyEntryUploadResponse,
)
from app.modules.daily_task_entry.service import DailyEntryService


router = APIRouter()


@router.get('/draft', response_model=DailyEntryDraftResponse)
def draft(entry_date: date = Query(...), user_id: UUID | None = None, db: Session = Depends(get_db), current_user=Depends(get_current_user)):
    service = DailyEntryService(db)
    entry, limits = service.draft(current_user, entry_date, user_id)
    return {'entry': service._to_base_schema(entry), 'limits': limits, 'existing_entry_id': entry.id if entry.id else None}


@router.get('/daily-entries/load', response_model=DailyEntryLoadResponse)
def load_daily_entries(entry_date: date = Query(...), user_id: UUID | None = None, db: Session = Depends(get_db), current_user=Depends(get_current_user)):
    service = DailyEntryService(db)
    items = service.load(current_user, entry_date, user_id)
    return {'entry_date': entry_date, 'limits': service.limits(), 'items': items}


@router.post('/daily-entries/upload', response_model=DailyEntryUploadResponse)
def upload_daily_entries(payload: DailyEntryUploadRequest, db: Session = Depends(get_db), current_user=Depends(get_current_user)):
    service = DailyEntryService(db)
    results = service.upload(current_user, payload.entries)
    return {'results': results}


@router.post('/entries', response_model=DailyEntryResponse)
def save_entry(payload: DailyEntryCreate, db: Session = Depends(get_db), current_user=Depends(get_current_user)):
    service = DailyEntryService(db)
    return service.serialize(service.save(current_user, payload))


@router.get('/entries', response_model=DailyEntryListResponse)
def entries(date_from: date | None = None, date_to: date | None = None, user_id: UUID | None = None, db: Session = Depends(get_db), current_user=Depends(get_current_user)):
    service = DailyEntryService(db)
    items, total = service.list_entries(current_user, date_from=date_from, date_to=date_to, user_id=user_id)
    return {'items': [service.serialize(item) for item in items], 'total': total, 'limits': service.limits()}


@router.get('/sla-review', response_model=DailyEntrySLAReviewResponse)
def sla_review(user_id: UUID = Query(...), entry_date: date = Query(...), db: Session = Depends(get_db), current_user=Depends(get_current_user)):
    # Admin-only score-review function; enforced inside the service so the
    # guard lives alongside the rest of the PMS authorization rules.
    service = DailyEntryService(db)
    return service.sla_review(current_user, user_id, entry_date)