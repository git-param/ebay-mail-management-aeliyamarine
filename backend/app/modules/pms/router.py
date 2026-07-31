from datetime import date
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.dependencies import get_current_user
from app.db.session import get_db
from app.modules.pms.schemas import PMSDailyEntryCreate, PMSDailyEntryResponse, PMSDraftResponse, PMSListResponse
from app.modules.pms.service import PMSService


router = APIRouter()


@router.get('/draft', response_model=PMSDraftResponse)
def draft(entry_date: date = Query(...), user_id: UUID | None = None, db: Session = Depends(get_db), current_user=Depends(get_current_user)):
    service = PMSService(db)
    entry, limits = service.draft(current_user, entry_date, user_id)
    existing_id = entry.id
    data = {
        'entry_date': entry.entry_date,
        'day_type': entry.day_type.value,
        'sold_posting_score': entry.sold_posting_score or 0,
        'm2m_vip_followups_score': entry.m2m_vip_followups_score or 0,
        'tracking_sheet_score': entry.tracking_sheet_score or 0,
        'purchase_sheet_score': entry.purchase_sheet_score or 0,
        'booking_score': entry.booking_score or 0,
        'other_general_work_score': entry.other_general_work_score or 0,
        'final_score_percent': entry.final_score_percent or 0,
        'sla_score': entry.sla_score or 0,
        'score_items': entry.score_items or [],
        'error_level': entry.error_level.value,
        'error_remark': entry.error_remark,
        'feedback_status': entry.feedback_status.value,
        'particulars_error_note': entry.particulars_error_note,
        'sla_remarks': entry.sla_remarks,
    }
    return {'entry': data, 'limits': limits, 'existing_entry_id': existing_id}


@router.post('/entries', response_model=PMSDailyEntryResponse)
def save_entry(payload: PMSDailyEntryCreate, db: Session = Depends(get_db), current_user=Depends(get_current_user)):
    service = PMSService(db)
    return service.serialize(service.save(current_user, payload))


@router.get('/entries', response_model=PMSListResponse)
def entries(date_from: date | None = None, date_to: date | None = None, user_id: UUID | None = None, db: Session = Depends(get_db), current_user=Depends(get_current_user)):
    service = PMSService(db)
    items, total = service.list_entries(current_user, date_from=date_from, date_to=date_to, user_id=user_id)
    return {'items': [service.serialize(item) for item in items], 'total': total, 'limits': service.limits()}
