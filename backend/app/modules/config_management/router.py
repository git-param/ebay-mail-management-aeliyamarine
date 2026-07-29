from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.api.dependencies import require_admin
from app.db.session import get_db
from app.modules.config_management.service import ConfigService


router = APIRouter()


class ConfigSettingResponse(BaseModel):
    section: str
    config_key: str
    label: str
    value: str
    value_type: str
    description: str | None = None
    is_editable: bool

    class Config:
        from_attributes = True


class ConfigUpdateItem(BaseModel):
    config_key: str
    value: str


class ConfigUpdateRequest(BaseModel):
    settings: list[ConfigUpdateItem]


class AccountSyncStateResponse(BaseModel):
    id: UUID
    account_name: str
    ebay_username: str
    store_name: str | None = None
    last_sync_at: datetime | None = None
    last_order_sync_at: datetime | None = None
    sync_status: str | None = None

    class Config:
        from_attributes = True


class AccountSyncUpdateRequest(BaseModel):
    account_id: UUID | None = None
    apply_to_all: bool = False
    last_sync_at: datetime | None = None


class DeleteConversationsRequest(BaseModel):
    confirmation: str


@router.get('', response_model=list[ConfigSettingResponse])
def list_config(db: Session = Depends(get_db), current_user=Depends(require_admin)):
    _ = current_user
    return ConfigService(db).list_settings()


@router.put('', response_model=list[ConfigSettingResponse])
def update_config(payload: ConfigUpdateRequest, db: Session = Depends(get_db), current_user=Depends(require_admin)):
    return ConfigService(db).update_settings([item.model_dump() for item in payload.settings], current_user)


@router.get('/account-sync', response_model=list[AccountSyncStateResponse])
def list_account_sync(db: Session = Depends(get_db), current_user=Depends(require_admin)):
    _ = current_user
    return ConfigService(db).list_account_sync_states()


@router.put('/account-sync')
def update_account_sync(payload: AccountSyncUpdateRequest, db: Session = Depends(get_db), current_user=Depends(require_admin)):
    _ = current_user
    return ConfigService(db).update_account_sync_cursor(account_id=payload.account_id, last_sync_at=payload.last_sync_at, apply_to_all=payload.apply_to_all)


@router.delete('/conversation-data')
def delete_conversation_data(payload: DeleteConversationsRequest, db: Session = Depends(get_db), current_user=Depends(require_admin)):
    _ = current_user
    if payload.confirmation.strip() != 'DELETE CONVERSATIONS':
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail='Type DELETE CONVERSATIONS to confirm.')
    return ConfigService(db).delete_conversation_data()
