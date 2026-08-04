from datetime import date
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.dependencies import get_current_user
from app.db.session import get_db
from app.modules.pms.schemas import (
    PMSDailyEntryCreate,
    PMSDailyEntryResponse,
    PMSDraftResponse,
    PMSListResponse,
    PMSLoadResponse,
    PMSUploadRequest,
    PMSUploadResponse,
)
from app.modules.pms.service import PMSService


router = APIRouter()


@router.get('/draft', response_model=PMSDraftResponse)
def draft(entry_date: date = Query(...), user_id: UUID | None = None, db: Session = Depends(get_db), current_user=Depends(get_current_user)):
    service = PMSService(db)
    entry, limits = service.draft(current_user, entry_date, user_id)
    return {'entry': service._to_base_schema(entry), 'limits': limits, 'existing_entry_id': entry.id if entry.id else None}


@router.get('/daily-entries/load', response_model=PMSLoadResponse)
def load_daily_entries(entry_date: date = Query(...), user_id: UUID | None = None, db: Session = Depends(get_db), current_user=Depends(get_current_user)):
    service = PMSService(db)
    items = service.load(current_user, entry_date, user_id)
    return {'entry_date': entry_date, 'limits': service.limits(), 'items': items}


@router.post('/daily-entries/upload', response_model=PMSUploadResponse)
def upload_daily_entries(payload: PMSUploadRequest, db: Session = Depends(get_db), current_user=Depends(get_current_user)):
    service = PMSService(db)
    results = service.upload(current_user, payload.entries)
    return {'results': results}


@router.post('/entries', response_model=PMSDailyEntryResponse)
def save_entry(payload: PMSDailyEntryCreate, db: Session = Depends(get_db), current_user=Depends(get_current_user)):
    service = PMSService(db)
    return service.serialize(service.save(current_user, payload))


@router.get('/entries', response_model=PMSListResponse)
def entries(date_from: date | None = None, date_to: date | None = None, user_id: UUID | None = None, db: Session = Depends(get_db), current_user=Depends(get_current_user)):
    service = PMSService(db)
    items, total = service.list_entries(current_user, date_from=date_from, date_to=date_to, user_id=user_id)
    return {'items': [service.serialize(item) for item in items], 'total': total, 'limits': service.limits()}