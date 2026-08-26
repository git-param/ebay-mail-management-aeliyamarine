from datetime import date
from uuid import UUID

from fastapi import APIRouter, Depends, File, Query, Response, UploadFile, status
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.api.dependencies import get_current_user
from app.db.session import get_db
from app.modules.offer_management.export import export_entries
from app.modules.offer_management.excel_import_service import OfferExcelImportService
from app.modules.offer_management.models import OfferManagementEntry, OfferManagementOutcome, OfferManagementStatus
from app.modules.offer_management.permissions import require_offer_history_access
from app.modules.offer_management.schemas import (
    OfferEntryCreate,
    OfferEntryHistoryResponse,
    OfferEntryListResponse,
    OfferEntryResponse,
    OfferEntryUpdate,
    OfferBulkDeleteRequest,
    OfferBulkDeleteResponse,
    OfferImportResponse,
    OfferLookupResponse,
    OfferSummaryResponse,
)
from app.modules.offer_management.service import OfferManagementService
from app.modules.offer_management.utils import excel_date_token


router = APIRouter()


def serialize_entry(entry) -> OfferEntryResponse:
    data = OfferEntryResponse.model_validate(entry).model_dump()
    data['agent_name'] = entry.created_by.full_name if entry.created_by else None
    data['related_conversation_ref'] = entry.related_conversation.provider_conversation_id if entry.related_conversation else None
    return OfferEntryResponse(**data)


def collect_filters(
    from_date: date | None = None,
    to_date: date | None = None,
    created_by_user_id: UUID | None = None,
    ebay_account_id: UUID | None = None,
    status: OfferManagementStatus | None = None,
    outcome: OfferManagementOutcome | None = None,
    next_offer_followup: date | None = None,
    buyer_id: str | None = None,
    sku: str | None = None,
    listing_id: str | None = None,
    is_high_value: bool | None = None,
    currency: str | None = None,
    search: str | None = None,
):
    return locals()


@router.post('', response_model=OfferEntryResponse)
def create_entry(payload: OfferEntryCreate, db: Session = Depends(get_db), current_user=Depends(get_current_user)):
    return serialize_entry(OfferManagementService(db).create(payload, current_user))


@router.get('', response_model=OfferEntryListResponse)
def list_entries(
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
    page: int = Query(1, ge=1),
    page_size: int = Query(25, ge=1, le=200),
    sort_by: str = 'updated_at',
    sort_order: str = 'desc',
    filters: dict = Depends(collect_filters),
):
    service = OfferManagementService(db)
    query = service.repo.query_entries(service.filters_for_user(filters, current_user), current_user)
    allowed_sort = {'entry_number', 'offer_date', 'listing_id', 'sku', 'status', 'updated_at', 'created_at'}
    sort_column = getattr(OfferManagementEntry, sort_by if sort_by in allowed_sort else 'updated_at')
    query = query.order_by(sort_column.asc() if sort_order == 'asc' else sort_column.desc())
    total = query.count()
    items = query.offset((page - 1) * page_size).limit(page_size).all()
    return {'items': [serialize_entry(item) for item in items], 'total': total, 'page': page, 'page_size': page_size}


@router.get('/lookup', response_model=OfferLookupResponse)
def lookup_listing(listing: str = Query(...), db: Session = Depends(get_db), current_user=Depends(get_current_user)):
    _ = current_user
    return OfferManagementService(db).lookup(listing)


@router.get('/summary', response_model=OfferSummaryResponse)
def summary(db: Session = Depends(get_db), current_user=Depends(get_current_user), filters: dict = Depends(collect_filters)):
    service = OfferManagementService(db)
    query = service.repo.query_entries(service.filters_for_user(filters, current_user), current_user)
    return service.repo.summary(query)


@router.get('/lookups')
def lookups(current_user=Depends(get_current_user)):
    _ = current_user
    return {
        'statuses': [
            OfferManagementStatus.OPEN.value,
            OfferManagementStatus.CLOSED.value,
        ],
        'outcomes': [
            OfferManagementOutcome.PENDING.value,
            OfferManagementOutcome.DONE.value,
            OfferManagementOutcome.IGNORE.value,
            OfferManagementOutcome.SOLD.value,
            OfferManagementOutcome.NOT_ABLE_TO_MATCH_THE_PRICE.value,
        ],
        'currencies': ['GBP', 'USD', 'EUR', 'INR', 'CAD', 'AUD', 'OTHER'],
    }


@router.get('/export')
def export(db: Session = Depends(get_db), current_user=Depends(get_current_user), filters: dict = Depends(collect_filters)):
    service = OfferManagementService(db)
    query = service.repo.query_entries(service.filters_for_user(filters, current_user), current_user).order_by(OfferManagementEntry.offer_date.asc())
    output = export_entries(query.all())
    token = excel_date_token(filters.get('from_date'), filters.get('to_date'))
    filename = f'offer-entries_{token}.xlsx'
    return StreamingResponse(
        output,
        media_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        headers={'Content-Disposition': f'attachment; filename="{filename}"'},
    )


@router.post('/import-excel', response_model=OfferImportResponse)
async def import_excel(file: UploadFile = File(...), db: Session = Depends(get_db), current_user=Depends(get_current_user)):
    return await OfferExcelImportService(db).import_file(file, current_user)


@router.get('/{entry_id}', response_model=OfferEntryResponse)
def read_entry(entry_id: UUID, db: Session = Depends(get_db), current_user=Depends(get_current_user)):
    return serialize_entry(OfferManagementService(db).get(entry_id, current_user))


@router.put('/{entry_id}', response_model=OfferEntryResponse)
def update_entry(entry_id: UUID, payload: OfferEntryUpdate, db: Session = Depends(get_db), current_user=Depends(get_current_user)):
    return serialize_entry(OfferManagementService(db).update(entry_id, payload, current_user))


@router.delete('/{entry_id}', status_code=status.HTTP_204_NO_CONTENT)
def delete_entry(entry_id: UUID, db: Session = Depends(get_db), current_user=Depends(get_current_user)):
    OfferManagementService(db).delete(entry_id, current_user)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post('/bulk-delete', response_model=OfferBulkDeleteResponse)
def bulk_delete_entries(payload: OfferBulkDeleteRequest, db: Session = Depends(get_db), current_user=Depends(get_current_user)):
    deleted_count = OfferManagementService(db).delete_many(payload.entry_ids, current_user)
    return {'deleted_count': deleted_count}


@router.get('/{entry_id}/history', response_model=list[OfferEntryHistoryResponse])
def entry_history(entry_id: UUID, db: Session = Depends(get_db), current_user=Depends(get_current_user)):
    require_offer_history_access(current_user)
    service = OfferManagementService(db)
    service.get(entry_id, current_user)
    rows = service.repo.history(entry_id)
    return [
        OfferEntryHistoryResponse(
            **OfferEntryHistoryResponse.model_validate(row).model_dump(exclude={'changed_by_name'}),
            changed_by_name=row.changed_by.full_name if row.changed_by else None,
        )
        for row in rows
    ]
