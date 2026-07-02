from datetime import date, datetime
from uuid import UUID
from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.api.dependencies import get_current_user, require_admin
from app.db.session import get_db
from app.schemas.message_type import MessageTypeCreate, MessageTypeResponse, MessageTypeStatus, MessageTypeUpdate
from app.services.audit_service import AuditService
from app.services.message_report_service import MessageReportService
from app.services.message_type_service import MessageTypeService

router = APIRouter()
reports_router = APIRouter()


def serialize_type(item):
    return {
        'id': item.id, 'name': item.name, 'parent_id': item.parent_id, 'description': item.description,
        'display_order': item.display_order, 'is_active': item.is_active, 'is_deleted': item.is_deleted,
        'created_at': item.created_at, 'updated_at': item.updated_at,
        'keywords': [keyword.keyword for keyword in item.keywords], 'children': [],
    }


@router.get('', response_model=list[MessageTypeResponse])
def list_types(include_deleted: bool = False, db: Session = Depends(get_db), current_user=Depends(get_current_user)):
    return MessageTypeService(db).tree(include_deleted=include_deleted)


@router.get('/tree', response_model=list[MessageTypeResponse])
def dropdown_tree(db: Session = Depends(get_db), current_user=Depends(get_current_user)):
    return MessageTypeService(db).tree(active_only=True)


@router.post('', response_model=MessageTypeResponse)
def create_type(payload: MessageTypeCreate, db: Session = Depends(get_db), current_user=Depends(require_admin)):
    item = MessageTypeService(db).create(payload, current_user.id)
    return serialize_type(item)


@router.put('/{item_id}', response_model=MessageTypeResponse)
def update_type(item_id: UUID, payload: MessageTypeUpdate, db: Session = Depends(get_db), current_user=Depends(require_admin)):
    item = MessageTypeService(db).update(item_id, payload, current_user.id); return serialize_type(item)


@router.delete('/{item_id}')
def delete_type(item_id: UUID, db: Session = Depends(get_db), current_user=Depends(require_admin)):
    item = MessageTypeService(db).delete(item_id, current_user.id); return {'id': item.id, 'is_active': item.is_active, 'is_deleted': item.is_deleted}


@router.patch('/{item_id}/status')
def status_type(item_id: UUID, payload: MessageTypeStatus, db: Session = Depends(get_db), current_user=Depends(require_admin)):
    service = MessageTypeService(db); item = service.repo.get(item_id)
    if not item: from fastapi import HTTPException; raise HTTPException(404, 'Message type not found')
    old = {'is_active': item.is_active, 'is_deleted': item.is_deleted}
    if payload.restore: item.is_deleted = False
    if payload.is_active is not None: item.is_active = payload.is_active
    AuditService(db).log(action='MESSAGE_TYPE_STATUS_CHANGED', user_id=current_user.id, entity_type='MESSAGE_TYPE', entity_id=item.id, metadata={'old': old, 'new': {'is_active': item.is_active, 'is_deleted': item.is_deleted}})
    db.commit(); return {'id': item.id, 'is_active': item.is_active, 'is_deleted': item.is_deleted}


def filters(date_from=None, date_to=None, seller_account_id=None, user_id=None, category_id=None, subcategory_id=None, conversation_id=None, search=None):
    return locals()


def report_filters(current_user, **kwargs):
    """Force agent report queries to the authenticated agent's records."""
    from app.api.dependencies import is_support_agent
    if is_support_agent(current_user):
        kwargs['user_id'] = current_user.id
    return kwargs


@reports_router.get('/message-types')
def report(date_from: date | None=None, date_to: date | None=None, seller_account_id: UUID | None=None,
           user_id: UUID | None=None, category_id: UUID | None=None, subcategory_id: UUID | None=None,
           conversation_id: UUID | None=None, search: str | None=None, limit: int=Query(50, ge=1, le=500),
           offset: int=Query(0, ge=0), sort_by: str='created_at', sort_dir: str=Query('desc', pattern='^(asc|desc)$'),
           db: Session=Depends(get_db), current_user=Depends(get_current_user)):
    scoped = report_filters(current_user, **filters(date_from,date_to,seller_account_id,user_id,category_id,subcategory_id,conversation_id,search))
    return MessageReportService(db).report(scoped, limit, offset, sort_by, sort_dir)


@reports_router.get('/message-types/export')
def export_report(date_from: date | None=None, date_to: date | None=None, seller_account_id: UUID | None=None,
                  user_id: UUID | None=None, category_id: UUID | None=None, subcategory_id: UUID | None=None,
                  conversation_id: UUID | None=None, search: str | None=None, db: Session=Depends(get_db), current_user=Depends(get_current_user)):
    scoped = report_filters(current_user, **filters(date_from,date_to,seller_account_id,user_id,category_id,subcategory_id,conversation_id,search))
    stream = MessageReportService(db).export(scoped)
    filename = f'message_report_{datetime.now().strftime("%Y_%m_%d")}.xlsx'
    return StreamingResponse(stream, media_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet', headers={'Content-Disposition': f'attachment; filename="{filename}"'})
