from datetime import UTC, datetime
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, model_validator
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.dependencies import get_current_user, is_admin
from app.db.session import get_db
from app.models.message_type import MessageType
from app.modules.task_management.models import MainTask


router = APIRouter()
AUTOMATIC_SOURCES = {'MESSAGE_TYPE', 'SOLD_POSTING', 'OFFER_MANAGEMENT'}
SOURCES = AUTOMATIC_SOURCES | {'MANUAL', 'OTHER'}


class MainTaskPayload(BaseModel):
    name: str = Field(min_length=1, max_length=160)
    source_type: str
    message_type_id: UUID | None = None
    weight: float = Field(gt=0, le=100)
    is_active: bool = True

    @model_validator(mode='after')
    def validate_source(self):
        if self.source_type not in SOURCES:
            raise ValueError('Invalid task source')
        if self.source_type == 'MESSAGE_TYPE' and not self.message_type_id:
            raise ValueError('Select a message type')
        if self.source_type != 'MESSAGE_TYPE' and self.message_type_id:
            raise ValueError('Only message type tasks can link to a message type')
        return self


class MainTaskResponse(MainTaskPayload):
    id: UUID
    model_config = {'from_attributes': True}


def require_admin(user) -> None:
    if not is_admin(user):
        raise HTTPException(status_code=403, detail='Only admins can manage main tasks')


def validate_message_type(db: Session, payload: MainTaskPayload) -> None:
    if payload.message_type_id:
        item = db.get(MessageType, payload.message_type_id)
        if not item or not item.is_active or item.is_deleted:
            raise HTTPException(status_code=422, detail='Select an active message type')


@router.get('/main-tasks', response_model=list[MainTaskResponse])
def list_main_tasks(db: Session = Depends(get_db), current_user=Depends(get_current_user)):
    query = select(MainTask).order_by(MainTask.created_at, MainTask.name)
    if not is_admin(current_user):
        query = query.where(MainTask.is_active.is_(True))
    return list(db.scalars(query))


@router.post('/main-tasks', response_model=MainTaskResponse, status_code=201)
def create_main_task(payload: MainTaskPayload, db: Session = Depends(get_db), current_user=Depends(get_current_user)):
    require_admin(current_user)
    if payload.source_type == 'OTHER' or payload.name.strip().casefold() == 'other':
        raise HTTPException(status_code=422, detail='Other is already available')
    validate_message_type(db, payload)
    if db.scalar(select(MainTask.id).where(func.lower(MainTask.name) == payload.name.strip().lower())):
        raise HTTPException(status_code=409, detail='Task name already exists')
    task = MainTask(**{**payload.model_dump(), 'name': payload.name.strip()})
    db.add(task)
    db.commit()
    db.refresh(task)
    return task


@router.put('/main-tasks/{task_id}', response_model=MainTaskResponse)
def update_main_task(task_id: UUID, payload: MainTaskPayload, db: Session = Depends(get_db), current_user=Depends(get_current_user)):
    require_admin(current_user)
    task = db.get(MainTask, task_id)
    if not task:
        raise HTTPException(status_code=404, detail='Task not found')
    if task.source_type == 'OTHER' and (payload.source_type != 'OTHER' or payload.name.strip().casefold() != 'other' or not payload.is_active):
        raise HTTPException(status_code=422, detail='Other must remain available')
    if task.source_type != 'OTHER' and (payload.source_type == 'OTHER' or payload.name.strip().casefold() == 'other'):
        raise HTTPException(status_code=422, detail='Other is already available')
    validate_message_type(db, payload)
    duplicate = db.scalar(select(MainTask.id).where(func.lower(MainTask.name) == payload.name.strip().lower(), MainTask.id != task_id))
    if duplicate:
        raise HTTPException(status_code=409, detail='Task name already exists')
    for field, value in payload.model_dump().items():
        setattr(task, field, payload.name.strip() if field == 'name' else value)
    task.updated_at = datetime.now(UTC)
    db.commit()
    db.refresh(task)
    return task
