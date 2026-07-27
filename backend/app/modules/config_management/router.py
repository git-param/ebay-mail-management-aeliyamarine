from fastapi import APIRouter, Depends
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


@router.get('', response_model=list[ConfigSettingResponse])
def list_config(db: Session = Depends(get_db), current_user=Depends(require_admin)):
    _ = current_user
    return ConfigService(db).list_settings()


@router.put('', response_model=list[ConfigSettingResponse])
def update_config(payload: ConfigUpdateRequest, db: Session = Depends(get_db), current_user=Depends(require_admin)):
    return ConfigService(db).update_settings([item.model_dump() for item in payload.settings], current_user)
