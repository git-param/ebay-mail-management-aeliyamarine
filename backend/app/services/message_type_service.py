from uuid import UUID
from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.models.message_type import MessageType
from app.repositories.message_type_repository import MessageTypeRepository
from app.services.audit_service import AuditService


class MessageTypeService:
    def __init__(self, db: Session): self.db, self.repo = db, MessageTypeRepository(db)

    def tree(self, include_deleted=False, active_only=False):
        items = self.repo.list(include_deleted)
        if active_only: items = [x for x in items if x.is_active and not x.is_deleted]
        by_parent = {}
        for item in items: by_parent.setdefault(item.parent_id, []).append(item)
        def node(item):
            return {'id': item.id, 'name': item.name, 'parent_id': item.parent_id, 'description': item.description,
                    'display_order': item.display_order, 'is_active': item.is_active, 'is_deleted': item.is_deleted,
                    'created_at': item.created_at, 'updated_at': item.updated_at,
                    'children': [node(child) for child in by_parent.get(item.id, [])]}
        return [node(root) for root in by_parent.get(None, [])]

    def create(self, payload, actor_id):
        if payload.parent_id and not self.repo.get(payload.parent_id): raise HTTPException(422, 'Parent message type not found')
        item = MessageType(**payload.model_dump(), created_by=actor_id); self.db.add(item); self.db.flush()
        AuditService(self.db).log(action='MESSAGE_TYPE_CREATED', user_id=actor_id, entity_type='MESSAGE_TYPE', entity_id=item.id, metadata={'new': payload.model_dump(mode='json')})
        self.db.commit(); self.db.refresh(item); return item

    def update(self, item_id, payload, actor_id):
        item = self.repo.get(item_id)
        if not item: raise HTTPException(404, 'Message type not found')
        changes = payload.model_dump(exclude_unset=True)
        parent_id = changes.get('parent_id')
        if parent_id and not self.repo.get(parent_id): raise HTTPException(422, 'Parent message type not found')
        if parent_id == item.id or (parent_id and parent_id in self.repo.descendants(item.id)): raise HTTPException(422, 'Circular message type hierarchy is not allowed')
        old = {key: str(getattr(item, key)) if getattr(item, key) is not None else None for key in changes}
        for key, value in changes.items(): setattr(item, key, value)
        AuditService(self.db).log(action='MESSAGE_TYPE_UPDATED', user_id=actor_id, entity_type='MESSAGE_TYPE', entity_id=item.id, metadata={'old': old, 'new': payload.model_dump(mode='json', exclude_unset=True)})
        self.db.commit(); self.db.refresh(item); return item

    def delete(self, item_id, actor_id):
        item = self.repo.get(item_id)
        if not item: raise HTTPException(404, 'Message type not found')
        family_ids = {item_id} | self.repo.descendants(item_id)
        if any(self.repo.used(type_id) for type_id in family_ids): item.is_active = False; action = 'MESSAGE_TYPE_DISABLED'
        else: item.is_deleted = True; item.is_active = False; action = 'MESSAGE_TYPE_DELETED'
        AuditService(self.db).log(action=action, user_id=actor_id, entity_type='MESSAGE_TYPE', entity_id=item.id)
        self.db.commit(); return item
